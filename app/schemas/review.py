"""Schemas defining the code review output contract.

These models are the single source of truth for what a review looks like.
In Phase 4 the same models will be handed to the OpenAI SDK, which turns
them into a JSON Schema the LLM must follow, and then validates the LLM's
reply against them. Later, the API layer will reuse them as the response
model. One definition, three consumers: change it here and everything
stays in sync.
"""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

# Upper bound on submitted code. Without one, a single request could send
# megabytes to a paid API. 20k characters is roughly 5k tokens: enough for a
# sizeable file, small enough to keep cost and latency predictable.
MAX_CODE_CHARS = 20_000


class Severity(StrEnum):
    """How much an issue matters. Ordered from least to most urgent."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Category(StrEnum):
    """What kind of problem an issue is."""

    BUG = "bug"
    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"


class _StrictModel(BaseModel):
    # Shared config for every model in the contract.
    #
    # - extra="forbid": reject unknown fields instead of silently dropping
    #   them. If the LLM invents a field, we want a loud error, not data
    #   loss. It also makes the generated JSON Schema say
    #   `additionalProperties: false`, which OpenAI's strict
    #   structured-output mode requires.
    # - str_strip_whitespace: "   " becomes "" before validation, so the
    #   min_length check catches whitespace-only strings too.
    #
    # (A comment, not a docstring, so it doesn't leak into the schema.)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReviewIssue(_StrictModel):
    """A single problem found in the reviewed code."""

    # NOTE: class docstrings AND every Field(description=...) below are copied
    # into the JSON Schema that Phase 4 sends to the LLM, so they act as
    # prompt text. Write them for the model; keep implementation notes in
    # `#` comments like this one, which are not sent.

    severity: Severity = Field(
        description=(
            "How serious the issue is: 'high' for crashes, data loss or "
            "security holes; 'medium' for likely bugs or notable "
            "inefficiency; 'low' for minor improvements."
        )
    )
    category: Category = Field(
        description="The kind of issue: bug, security, performance or style."
    )
    # Required-but-nullable, NOT `= None`: OpenAI strict mode demands every
    # property appear in `required`, so "no line" must be an explicit null
    # from the model rather than an omitted key.
    line_number: int | None = Field(
        ge=1,
        description=(
            "1-based line number where the issue occurs, read from the "
            "'N: ' prefix on each line of the submitted code. Use null when "
            "the issue is not tied to a single line (for example, a problem "
            "with the code as a whole)."
        ),
    )
    description: str = Field(
        min_length=1,
        description="A short, specific explanation of what is wrong and why it matters.",
    )
    suggested_fix: str = Field(
        min_length=1,
        description="A concrete change that would resolve the issue.",
    )


class ReviewResponse(_StrictModel):
    """The full result of reviewing one piece of code."""

    # `issues` is declared before `summary` on purpose. LLMs generate JSON
    # field by field, in schema order, so putting the summary last means the
    # model writes it after it has already listed what it found, and the
    # summary is more likely to agree with the issues.

    issues: list[ReviewIssue] = Field(
        description=(
            "Every issue found, in the order they appear in the code. "
            "An empty list means no issues were found."
        )
    )
    summary: str = Field(
        min_length=1,
        description="A one-to-three sentence overall assessment of the code.",
    )


class ReviewRequest(BaseModel):
    """The input to POST /review: code to review plus a language hint."""

    # Deliberately NOT _StrictModel: str_strip_whitespace would strip the
    # indentation off the first line of the code and shift how it looks to the
    # model. `code` must reach the reviewer byte-for-byte; only `language`
    # (a short label) is stripped, via its own constraint below.
    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        min_length=1,
        max_length=MAX_CODE_CHARS,
        description="The source code to review, as raw text.",
    )
    language: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
    ] | None = Field(
        default=None,
        description=(
            "Programming language of the code, e.g. 'python' or 'js'. Optional: "
            "if omitted, it is inferred from `filename`, or failing that the "
            "model identifies it from the code."
        ),
    )
    filename: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=260)
    ] | None = Field(
        default=None,
        description=(
            "Optional file name or path, e.g. 'app/main.py'. Used only to infer "
            "the language from its extension when `language` isn't given."
        ),
    )

    @field_validator("code")
    @classmethod
    def code_must_not_be_blank(cls, value: str) -> str:
        """Reject whitespace-only code without altering the code itself."""
        if not value.strip():
            raise ValueError("code must contain something other than whitespace")
        return value
