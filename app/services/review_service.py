"""The review use case: turn submitted code into a validated ReviewResponse.

This is the only module that talks to OpenAI. It knows nothing about HTTP
(no FastAPI imports); the router calls it and translates its errors into
status codes. That split lets us test the LLM logic without a web server,
and swap the web layer without touching the LLM logic.
"""

import logging
from collections.abc import Sequence

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    ContentFilterFinishReasonError,
    LengthFinishReasonError,
)
from openai.types.chat import ParsedChatCompletion
from pydantic import ValidationError

from app.schemas.review import ReviewResponse
from app.services.exceptions import (
    LLMResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.services.languages import resolve_language
from app.services.line_numbering import NumberedLine, number_lines
from app.services.prompts import build_system_prompt, build_user_message

logger = logging.getLogger(__name__)

# Cap on generated tokens. Generous for a review (each issue is ~60 tokens)
# but bounded, so a runaway generation can't burn unlimited money.
MAX_OUTPUT_TOKENS = 4096


class ReviewService:
    """Reviews code by calling an OpenAI model with structured outputs."""

    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        # The client is injected rather than created here, so tests can pass
        # a fake and the app can share one client (and its connection pool)
        # across all requests.
        self._client = client
        self._model = model

    async def review_code(
        self, code: str, language: str | None = None, filename: str | None = None
    ) -> ReviewResponse:
        """Review a whole piece of code; line numbers count from 1.

        The language comes from `language` if given, else from `filename`'s
        extension, else the model is asked to identify it.

        Raises:
            LLMTimeoutError: the API did not respond in time.
            LLMUnavailableError: the API call failed.
            LLMResponseError: the API responded with an unusable result.
        """
        return await self.review_lines(
            number_lines(code), resolve_language(language, filename)
        )

    async def review_lines(
        self,
        lines: Sequence[NumberedLine],
        language: str | None,
        *,
        excerpt: bool = False,
    ) -> ReviewResponse:
        """Review `lines`, each carrying its real line number in the file.

        Whole-file review passes lines numbered 1..N. Pull-request review
        passes only the added lines, with their true (skipping) numbers.
        Either way the model reads the numbers from the text, and the same
        set of numbers is used afterwards to check what it reported.

        Set `excerpt=True` when `lines` are part of a larger file, so the
        model knows not to judge code it can't see.

        Raises: the same errors as `review_code`.
        """
        messages = [
            {"role": "system", "content": build_system_prompt(language)},
            {"role": "user", "content": build_user_message(lines, language, excerpt=excerpt)},
        ]

        try:
            # `.parse()` with a Pydantic class does three things for us: it
            # converts the class to a strict JSON Schema, sends it as
            # `response_format` (so the model's output is constrained to that
            # shape), and parses the reply back into the class.
            completion = await self._client.chat.completions.parse(
                model=self._model,
                messages=messages,
                response_format=ReviewResponse,
                # Reviews should be consistent, not creative. Temperature 0
                # doesn't make output perfectly deterministic, but it's the
                # closest the API offers.
                temperature=0,
                max_completion_tokens=MAX_OUTPUT_TOKENS,
            )
        # Order matters: APITimeoutError is a subclass of APIConnectionError,
        # so the more specific one must be caught first.
        except APITimeoutError as exc:
            logger.warning("OpenAI request timed out: %s", exc)
            raise LLMTimeoutError(
                "The review timed out. Try again, or submit less code."
            ) from exc
        except APIConnectionError as exc:
            logger.error("Could not reach OpenAI: %s", exc)
            raise LLMUnavailableError(
                "Could not reach the review model. Try again shortly."
            ) from exc
        except APIStatusError as exc:
            # Non-2xx from OpenAI: bad key, rate limit, server error, etc.
            # Log the details for us; tell the client only that it failed.
            logger.error("OpenAI returned HTTP %s: %s", exc.status_code, exc.message)
            raise LLMUnavailableError(
                "The review model returned an error. Try again shortly."
            ) from exc
        except LengthFinishReasonError as exc:
            # Output hit max_completion_tokens: the JSON is cut off mid-way.
            logger.error("Review output was truncated at the token limit")
            raise LLMResponseError(
                "The review was too long to complete. Try submitting less code."
            ) from exc
        except ContentFilterFinishReasonError as exc:
            logger.error("Review output was blocked by the content filter")
            raise LLMResponseError(
                "The review was blocked by the model's content filter."
            ) from exc
        except ValidationError as exc:
            # The SDK's own parse step found the reply didn't match the schema.
            logger.error("SDK could not parse the model reply: %s", exc)
            raise LLMResponseError(
                "The model returned a review in an unexpected format."
            ) from exc

        review = self._validate(completion)
        return self._enforce_line_rules(review, lines)

    @staticmethod
    def _enforce_line_rules(
        review: ReviewResponse, lines: Sequence[NumberedLine]
    ) -> ReviewResponse:
        """Make the model's line numbers agree with what it was actually shown.

        The prompt *asks* the model to behave; this *guarantees* it. Two rules:

        1. An issue on a read-only context line is dropped. Context is shown
           only for understanding, so a finding there is about code the pull
           request didn't touch, which is out of scope. (Dropped, not nulled:
           nulling would keep a finding about unchanged code.)
        2. A line number the model was never shown becomes null. The schema
           can only say "an integer >= 1"; it can't know how long this code
           is. Models occasionally cite a line past the end, or one in a gap.
           That would point a reader at the wrong code, whereas null honestly
           says "not tied to a specific line", which the contract allows. The
           issue itself is kept: the problem may be real though mislocated.

        Whole-file review has no context lines, so only rule 2 applies there.
        """
        shown = {line.number for line in lines}
        context = {line.number for line in lines if line.context}

        kept = []
        for issue in review.issues:
            number = issue.line_number
            if number in context:
                logger.warning(
                    "Model reported an issue on read-only context line %s; dropping it", number
                )
                continue
            if number is not None and number not in shown:
                logger.warning(
                    "Model cited line %s, which was not in the submitted code; "
                    "setting line_number to null",
                    number,
                )
                issue = issue.model_copy(update={"line_number": None})
            kept.append(issue)
        return review.model_copy(update={"issues": kept})

    @staticmethod
    def _validate(completion: ParsedChatCompletion[ReviewResponse]) -> ReviewResponse:
        """Check the raw reply ourselves and return a ReviewResponse.

        Structured outputs make a malformed reply very unlikely, but they are
        someone else's guarantee, so we don't lean on them alone. Checking the
        raw text with our own model means the contract is enforced by code we
        own, even if SDK parsing behavior or server-side schema enforcement
        changes (or quietly ignores a keyword like `minimum`).
        """
        if not completion.choices:
            logger.error("OpenAI returned no choices")
            raise LLMResponseError("The model returned no review.")

        message = completion.choices[0].message

        # With structured outputs, a refusal arrives in `refusal` instead of
        # `content`. It is a normal, non-error API response; we must check.
        if message.refusal:
            logger.warning("Model refused the request: %s", message.refusal)
            raise LLMResponseError("The model declined to review this code.")

        if not message.content:
            logger.error("OpenAI reply had empty content")
            raise LLMResponseError("The model returned an empty review.")

        try:
            return ReviewResponse.model_validate_json(message.content)
        except ValidationError as exc:
            logger.error("Model reply failed schema validation: %s", exc)
            raise LLMResponseError(
                "The model returned a review in an unexpected format."
            ) from exc
