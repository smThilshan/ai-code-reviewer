"""Schemas for POST /review-pr: the request, and the per-file review results."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.review import ReviewResponse


class PullRequestReviewRequest(BaseModel):
    """The input to POST /review-pr."""

    model_config = ConfigDict(extra="forbid")

    pr_url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)] = (
        Field(description="URL of a public GitHub pull request, e.g. https://github.com/owner/repo/pull/123.")
    )


class ExcerptLine(BaseModel):
    """One line shown to the model for this file: an added line, or read-only context.

    This is exactly what ReviewService was given (see
    app.services.pr_review_service._review_one), exposed as-is rather than
    re-fetched, so a frontend can show the code a finding refers to without
    a second round trip or storing whole files.
    """

    line_number: int
    text: str
    is_context: bool = Field(
        default=False,
        description="True for unchanged lines shown only for context; false for lines the PR added or changed.",
    )


class FileReview(BaseModel):
    """The review of one changed file."""

    path: str = Field(description="File path within the repository.")
    language: str = Field(description="Language inferred from the file extension.")
    lines_reviewed: int = Field(
        description="How many added/changed lines were sent for review."
    )
    review: ReviewResponse | None = Field(
        description=(
            "Issues found in the added lines. Each issue's line_number is the "
            "line in the file as of the PR's head commit, or null. Null when "
            "the review of this file failed; see `error`."
        )
    )
    error: str | None = Field(
        description="Why this file could not be reviewed, if it couldn't."
    )
    excerpt: list[ExcerptLine] = Field(
        description="The lines sent to the model for this file, in file order."
    )


class SkippedFile(BaseModel):
    """A changed file that was deliberately not reviewed."""

    path: str
    reason: str


class PullRequestReviewResponse(BaseModel):
    """The review of a whole pull request."""

    pull_request: str = Field(description="Canonical URL of the reviewed pull request.")
    files: list[FileReview] = Field(description="One entry per file that was reviewed.")
    skipped_files: list[SkippedFile] = Field(
        description="Changed files that were not reviewed, and why."
    )
