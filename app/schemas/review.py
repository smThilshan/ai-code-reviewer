"""Schemas defining the code review output contract.

These models are the single source of truth for what a review looks like.
In Phase 4 the same models will be handed to the OpenAI SDK, which turns
them into a JSON Schema the LLM must follow, and then validates the LLM's
reply against them. Later, the API layer will reuse them as the response
model. One definition, three consumers: change it here and everything
stays in sync.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


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
    line_number: int = Field(
        ge=1,
        description=(
            "1-based line number in the submitted code where the issue "
            "occurs (the first line of the code is line 1)."
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
