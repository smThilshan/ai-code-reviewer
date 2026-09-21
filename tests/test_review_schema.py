"""Tests for the review output schema, run in isolation (no LLM, no API).

Each test pins down one rule of the contract. When Phase 4 makes the LLM
produce this shape, these tests are what tell us the contract itself is
still what we designed.
"""

import json

import pytest
from pydantic import ValidationError

from app.schemas.review import Category, ReviewIssue, ReviewResponse, Severity

VALID_ISSUE = {
    "severity": "high",
    "category": "security",
    "line_number": 12,
    "description": "User input is concatenated into an SQL query.",
    "suggested_fix": "Use a parameterized query instead of string formatting.",
}

VALID_REVIEW = {
    "issues": [
        VALID_ISSUE,
        {
            "severity": "low",
            "category": "style",
            "line_number": 3,
            "description": "Variable `x` has a non-descriptive name.",
            "suggested_fix": "Rename `x` to `user_count`.",
        },
    ],
    "summary": "One SQL injection risk and one naming nit. Fix the query first.",
}


def with_override(base: dict, **overrides: object) -> dict:
    """Copy `base` and replace some fields, to build one-thing-wrong inputs."""
    return {**base, **overrides}


# --- Happy path -------------------------------------------------------------


def test_valid_review_parses_into_typed_objects() -> None:
    review = ReviewResponse.model_validate(VALID_REVIEW)

    assert len(review.issues) == 2
    assert review.issues[0].severity is Severity.HIGH
    assert review.issues[0].category is Category.SECURITY
    assert review.issues[0].line_number == 12


def test_json_round_trip_is_lossless() -> None:
    review = ReviewResponse.model_validate(VALID_REVIEW)

    as_json = review.model_dump_json()
    restored = ReviewResponse.model_validate_json(as_json)

    assert restored == review
    # Enums serialize as plain strings, which is what the LLM and API clients see.
    assert json.loads(as_json)["issues"][0]["severity"] == "high"


def test_empty_issue_list_is_valid() -> None:
    """Clean code is a legitimate result, not an error."""
    review = ReviewResponse(issues=[], summary="No problems found.")

    assert review.issues == []


# --- Enum rejection ---------------------------------------------------------


@pytest.mark.parametrize("bad_severity", ["critical", "HIGH", "", "urgent", None, 2])
def test_invalid_severity_is_rejected(bad_severity: object) -> None:
    with pytest.raises(ValidationError):
        ReviewIssue.model_validate(with_override(VALID_ISSUE, severity=bad_severity))


@pytest.mark.parametrize("bad_category", ["logic", "Bug", "", None])
def test_invalid_category_is_rejected(bad_category: object) -> None:
    with pytest.raises(ValidationError):
        ReviewIssue.model_validate(with_override(VALID_ISSUE, category=bad_category))


# --- Line number ------------------------------------------------------------


@pytest.mark.parametrize("bad_line", [0, -1, "twelve", None, 1.5])
def test_invalid_line_number_is_rejected(bad_line: object) -> None:
    with pytest.raises(ValidationError):
        ReviewIssue.model_validate(with_override(VALID_ISSUE, line_number=bad_line))


def test_first_line_is_line_one() -> None:
    issue = ReviewIssue.model_validate(with_override(VALID_ISSUE, line_number=1))

    assert issue.line_number == 1


# --- Text fields ------------------------------------------------------------


@pytest.mark.parametrize("field", ["description", "suggested_fix"])
@pytest.mark.parametrize("empty", ["", "   ", "\n\t"])
def test_blank_issue_text_is_rejected(field: str, empty: str) -> None:
    with pytest.raises(ValidationError):
        ReviewIssue.model_validate(with_override(VALID_ISSUE, **{field: empty}))


def test_blank_summary_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ReviewResponse.model_validate(with_override(VALID_REVIEW, summary="  "))


# --- Structure --------------------------------------------------------------


@pytest.mark.parametrize(
    "missing", ["severity", "category", "line_number", "description", "suggested_fix"]
)
def test_missing_issue_field_is_rejected(missing: str) -> None:
    data = {k: v for k, v in VALID_ISSUE.items() if k != missing}

    with pytest.raises(ValidationError):
        ReviewIssue.model_validate(data)


@pytest.mark.parametrize("missing", ["issues", "summary"])
def test_missing_review_field_is_rejected(missing: str) -> None:
    data = {k: v for k, v in VALID_REVIEW.items() if k != missing}

    with pytest.raises(ValidationError):
        ReviewResponse.model_validate(data)


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ReviewIssue.model_validate(with_override(VALID_ISSUE, confidence=0.9))

    with pytest.raises(ValidationError):
        ReviewResponse.model_validate(with_override(VALID_REVIEW, author="gpt"))


def test_json_schema_is_strict_for_llm_structured_output() -> None:
    """Phase 4 hands this schema to the LLM. Guard the properties it needs."""
    schema = ReviewResponse.model_json_schema()
    issue_schema = schema["$defs"]["ReviewIssue"]

    for object_schema in (schema, issue_schema):
        assert object_schema["additionalProperties"] is False
        assert set(object_schema["required"]) == set(object_schema["properties"])

    # Field order is generation order: issues first, summary last.
    assert list(schema["properties"]) == ["issues", "summary"]
    assert schema["$defs"]["Severity"]["enum"] == ["low", "medium", "high"]


def test_one_bad_issue_invalidates_the_whole_review() -> None:
    bad_issue = with_override(VALID_ISSUE, severity="critical")
    data = with_override(VALID_REVIEW, issues=[VALID_ISSUE, bad_issue])

    with pytest.raises(ValidationError) as exc_info:
        ReviewResponse.model_validate(data)

    # The error points at the exact bad element: issues -> index 1 -> severity.
    assert exc_info.value.errors()[0]["loc"] == ("issues", 1, "severity")
