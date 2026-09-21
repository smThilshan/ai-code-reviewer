"""Tests for ReviewService using a fake OpenAI client (no network, no cost).

Each failure mode of the real API is simulated by making the fake's
`chat.completions.parse` raise or return something odd, then asserting the
service turns it into the right domain error rather than leaking a raw
SDK exception or bad data.
"""

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx2
import pytest
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    ContentFilterFinishReasonError,
    LengthFinishReasonError,
)
from pydantic import ValidationError

from app.schemas.review import ReviewResponse, Severity
from app.services.exceptions import (
    LLMResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.services.line_numbering import NumberedLine
from app.services.prompts import EXCERPT_NOTE, SYSTEM_PROMPT
from app.services.review_service import MAX_OUTPUT_TOKENS, ReviewService

REQUEST = httpx2.Request("POST", "https://api.openai.com/v1/chat/completions")

GOOD_REPLY = {
    "issues": [
        {
            "severity": "high",
            "category": "security",
            "line_number": 4,
            "description": "SQL built by string concatenation.",
            "suggested_fix": "Use a parameterized query.",
        },
        {
            "severity": "low",
            "category": "style",
            "line_number": None,
            "description": "No docstrings anywhere.",
            "suggested_fix": "Add docstrings to public functions.",
        },
    ],
    "summary": "One injection risk; otherwise readable.",
}


def completion_with(content: str | None, refusal: str | None = None) -> SimpleNamespace:
    """Shape of a ChatCompletion, reduced to the fields the service reads."""
    message = SimpleNamespace(content=content, refusal=refusal)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def make_service(
    result: Any = None, error: Exception | None = None
) -> tuple[ReviewService, AsyncMock]:
    """Build a ReviewService whose OpenAI client returns `result` or raises `error`."""
    parse = AsyncMock(return_value=result, side_effect=error)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))
    return ReviewService(client=client, model="test-model"), parse  # type: ignore[arg-type]


def review(service: ReviewService, code: str = "x = 1", language: str = "python"):
    return asyncio.run(service.review_code(code=code, language=language))


# --- Success ----------------------------------------------------------------


def test_returns_validated_review_response() -> None:
    service, _ = make_service(completion_with(json.dumps(GOOD_REPLY)))

    result = review(service)

    assert isinstance(result, ReviewResponse)
    assert result.issues[0].severity is Severity.HIGH
    assert result.issues[1].line_number is None  # null line number passes through


def test_sends_schema_prompt_and_line_numbered_code_to_the_model() -> None:
    service, parse = make_service(completion_with(json.dumps(GOOD_REPLY)))

    review(service, code="def foo():\n    pass", language="python")

    kwargs = parse.await_args.kwargs
    assert kwargs["model"] == "test-model"
    assert kwargs["response_format"] is ReviewResponse
    assert kwargs["temperature"] == 0
    assert kwargs["max_completion_tokens"] == MAX_OUTPUT_TOKENS

    system, user = kwargs["messages"]
    assert system == {"role": "system", "content": SYSTEM_PROMPT}
    assert user["role"] == "user"
    assert "Language: python" in user["content"]
    assert "1: def foo():\n2:     pass" in user["content"]  # numbered, not raw


# --- API call failures ------------------------------------------------------


def test_timeout_becomes_llm_timeout_error() -> None:
    service, _ = make_service(error=APITimeoutError(request=REQUEST))

    with pytest.raises(LLMTimeoutError):
        review(service)


def test_connection_failure_becomes_llm_unavailable_error() -> None:
    service, _ = make_service(error=APIConnectionError(request=REQUEST))

    with pytest.raises(LLMUnavailableError):
        review(service)


@pytest.mark.parametrize("status_code", [401, 429, 500, 503])
def test_http_error_from_openai_becomes_llm_unavailable_error(status_code: int) -> None:
    response = httpx2.Response(status_code, request=REQUEST)
    service, _ = make_service(error=APIStatusError("boom", response=response, body=None))

    with pytest.raises(LLMUnavailableError):
        review(service)


def test_raw_upstream_details_are_not_exposed_in_the_error_message() -> None:
    """A bad-key error must not leak the key or OpenAI's message to clients."""
    response = httpx2.Response(401, request=REQUEST)
    error = APIStatusError("Incorrect API key provided: sk-secret", response=response, body=None)
    service, _ = make_service(error=error)

    with pytest.raises(LLMUnavailableError) as exc_info:
        review(service)

    assert "sk-secret" not in str(exc_info.value)


# --- Unusable results -------------------------------------------------------


def test_truncated_output_becomes_llm_response_error() -> None:
    # The exception's constructor reads `completion.usage`, so give it that.
    error = LengthFinishReasonError(completion=SimpleNamespace(usage=None))  # type: ignore[arg-type]
    service, _ = make_service(error=error)

    with pytest.raises(LLMResponseError):
        review(service)


def test_content_filter_becomes_llm_response_error() -> None:
    service, _ = make_service(error=ContentFilterFinishReasonError())

    with pytest.raises(LLMResponseError):
        review(service)


def test_sdk_parse_failure_becomes_llm_response_error() -> None:
    try:
        ReviewResponse.model_validate({})
    except ValidationError as validation_error:
        service, _ = make_service(error=validation_error)

    with pytest.raises(LLMResponseError):
        review(service)


def test_refusal_becomes_llm_response_error() -> None:
    service, _ = make_service(completion_with(content=None, refusal="I can't help with that."))

    with pytest.raises(LLMResponseError, match="declined"):
        review(service)


@pytest.mark.parametrize("content", [None, ""])
def test_empty_content_becomes_llm_response_error(content: str | None) -> None:
    service, _ = make_service(completion_with(content))

    with pytest.raises(LLMResponseError):
        review(service)


def test_no_choices_becomes_llm_response_error() -> None:
    service, _ = make_service(SimpleNamespace(choices=[]))

    with pytest.raises(LLMResponseError):
        review(service)


def test_content_that_is_not_json_becomes_llm_response_error() -> None:
    service, _ = make_service(completion_with("Sure! Here is my review: ..."))

    with pytest.raises(LLMResponseError):
        review(service)


def test_content_violating_the_schema_is_caught_by_our_own_validation() -> None:
    """Belt-and-suspenders: the fake bypasses the SDK's parse, so only our own
    explicit validation stands between this bad reply and the caller."""
    bad = {**GOOD_REPLY, "issues": [{**GOOD_REPLY["issues"][0], "severity": "critical"}]}
    service, _ = make_service(completion_with(json.dumps(bad)))

    with pytest.raises(LLMResponseError):
        review(service)


def test_line_number_zero_is_caught_by_our_own_validation() -> None:
    bad = {**GOOD_REPLY, "issues": [{**GOOD_REPLY["issues"][0], "line_number": 0}]}
    service, _ = make_service(completion_with(json.dumps(bad)))

    with pytest.raises(LLMResponseError):
        review(service)


# --- Range check: line numbers the model was never shown ---------------------


def reply_citing_lines(*line_numbers: int | None) -> SimpleNamespace:
    """A model reply with one issue per given line number."""
    issues = [
        {**GOOD_REPLY["issues"][0], "line_number": number, "description": f"issue at {number}"}
        for number in line_numbers
    ]
    return completion_with(json.dumps({"issues": issues, "summary": "s"}))


def cited_lines(result: ReviewResponse) -> list[int | None]:
    return [issue.line_number for issue in result.issues]


def test_line_past_the_end_of_the_code_becomes_null() -> None:
    service, _ = make_service(reply_citing_lines(99))

    result = review(service, code="a\nb\nc")  # 3 lines

    assert cited_lines(result) == [None]
    assert result.issues[0].description == "issue at 99"  # the issue itself is kept


def test_last_line_and_first_line_are_kept() -> None:
    service, _ = make_service(reply_citing_lines(1, 3))

    result = review(service, code="a\nb\nc")

    assert cited_lines(result) == [1, 3]


def test_only_the_out_of_range_issues_are_nulled() -> None:
    service, _ = make_service(reply_citing_lines(2, 4, None, 50))

    result = review(service, code="a\nb\nc\nd")

    assert cited_lines(result) == [2, 4, None, None]


def test_trailing_newline_does_not_add_a_valid_line() -> None:
    """"a\\nb\\n" has 2 lines, so line 3 must not be accepted."""
    service, _ = make_service(reply_citing_lines(2, 3))

    result = review(service, code="a\nb\n")

    assert cited_lines(result) == [2, None]


def test_excerpt_lines_in_a_gap_are_nulled_but_shown_lines_kept() -> None:
    """For a PR excerpt, "valid" means shown to the model, not merely <= the max."""
    lines = [NumberedLine(10, "a"), NumberedLine(11, "b"), NumberedLine(40, "c")]
    service, _ = make_service(reply_citing_lines(10, 25, 40, 41))

    result = asyncio.run(service.review_lines(lines, "python", excerpt=True))

    assert cited_lines(result) == [10, None, 40, None]


def test_excerpt_sends_real_line_numbers_and_the_excerpt_note() -> None:
    lines = [NumberedLine(10, "a"), NumberedLine(40, "c")]
    service, parse = make_service(reply_citing_lines(10))

    asyncio.run(service.review_lines(lines, "python", excerpt=True))

    user_message = parse.await_args.kwargs["messages"][1]["content"]
    assert "10: a\n40: c" in user_message
    assert EXCERPT_NOTE in user_message


def test_whole_file_review_does_not_get_the_excerpt_note() -> None:
    service, parse = make_service(reply_citing_lines(1))

    review(service, code="a")

    assert EXCERPT_NOTE not in parse.await_args.kwargs["messages"][1]["content"]
