"""HTTP layer for reviewing GitHub pull requests.

Same shape as routers/review.py: thin. The service does the work; this file
maps its domain errors to HTTP status codes.
"""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status

from app.config import settings
from app.dependencies import get_pull_request_review_service
from app.rate_limit import limiter
from app.schemas.examples import PR_REVIEW_REQUEST_EXAMPLES
from app.schemas.pull_request import PullRequestReviewRequest, PullRequestReviewResponse
from app.services.exceptions import (
    GitHubAccessDeniedError,
    GitHubRateLimitError,
    GitHubTimeoutError,
    InvalidPullRequestURLError,
    LLMTimeoutError,
    NoReviewableChangesError,
    PullRequestError,
    PullRequestNotFoundError,
    PullRequestTooLargeError,
    ReviewError,
)
from app.services.pr_review_service import PullRequestReviewService

router = APIRouter(tags=["pull requests"])

# First matching entry wins; anything not listed is an upstream failure (502).
_STATUS_BY_ERROR: tuple[tuple[type[Exception], int], ...] = (
    (InvalidPullRequestURLError, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (NoReviewableChangesError, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (PullRequestTooLargeError, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (PullRequestNotFoundError, status.HTTP_404_NOT_FOUND),
    (GitHubAccessDeniedError, status.HTTP_403_FORBIDDEN),
    (GitHubRateLimitError, status.HTTP_503_SERVICE_UNAVAILABLE),
    (GitHubTimeoutError, status.HTTP_504_GATEWAY_TIMEOUT),
    (LLMTimeoutError, status.HTTP_504_GATEWAY_TIMEOUT),
)


def _status_for(exc: Exception) -> int:
    for error_type, status_code in _STATUS_BY_ERROR:
        if isinstance(exc, error_type):
            return status_code
    return status.HTTP_502_BAD_GATEWAY


@router.post(
    "/review-pr",
    response_model=PullRequestReviewResponse,
    summary="Review the code changes in a GitHub pull request",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "PR not found, or in a private repository."},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Invalid PR URL, PR too large, or no reviewable code changes."
        },
        status.HTTP_429_TOO_MANY_REQUESTS: {"description": "Per-IP rate limit exceeded."},
        status.HTTP_502_BAD_GATEWAY: {"description": "GitHub or the review model failed."},
        status.HTTP_504_GATEWAY_TIMEOUT: {"description": "GitHub or the review model timed out."},
    },
)
@limiter.limit(settings.review_pr_rate_limit)
async def review_pull_request(
    request: Request,  # required by slowapi; see routers/review.py
    response: Response,  # required for slowapi's rate-limit headers; see routers/review.py
    payload: Annotated[PullRequestReviewRequest, Body(openapi_examples=PR_REVIEW_REQUEST_EXAMPLES)],
    service: Annotated[PullRequestReviewService, Depends(get_pull_request_review_service)],
) -> PullRequestReviewResponse:
    """Fetch a PR's diff, review only the lines it adds or changes, per file."""
    try:
        return await service.review_pull_request(payload.pr_url)
    except (PullRequestError, ReviewError) as exc:
        raise HTTPException(status_code=_status_for(exc), detail=str(exc)) from exc
