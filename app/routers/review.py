"""HTTP layer for code review.

The route handler is intentionally thin: validate input (FastAPI does that
from the ReviewRequest type), call the service, translate the service's
domain errors into HTTP status codes. All actual review logic lives in
`app/services/review_service.py`.
"""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status

from app.config import settings
from app.dependencies import get_review_service
from app.rate_limit import limiter
from app.schemas.examples import REVIEW_REQUEST_EXAMPLES
from app.schemas.review import ReviewRequest, ReviewResponse
from app.services.exceptions import LLMTimeoutError, ReviewError
from app.services.review_service import ReviewService

router = APIRouter(tags=["review"])


@router.post(
    "/review",
    response_model=ReviewResponse,
    summary="Review a piece of code",
    responses={
        status.HTTP_429_TOO_MANY_REQUESTS: {"description": "Per-IP rate limit exceeded."},
        status.HTTP_502_BAD_GATEWAY: {
            "description": "The review model failed or returned an unusable result."
        },
        status.HTTP_504_GATEWAY_TIMEOUT: {
            "description": "The review model did not respond in time."
        },
    },
)
# Must sit BELOW @router.post: the router registers whatever function it is
# given, so the limiter has to have wrapped it already.
@limiter.limit(settings.review_rate_limit)
async def create_review(
    # slowapi finds the client IP through a parameter named exactly `request`
    # holding the Starlette Request, which is why the body is called `payload`.
    request: Request,
    payload: Annotated[ReviewRequest, Body(openapi_examples=REVIEW_REQUEST_EXAMPLES)],
    service: Annotated[ReviewService, Depends(get_review_service)],
) -> ReviewResponse:
    """Analyze the submitted code and return structured review findings."""
    try:
        return await service.review_code(code=payload.code, language=payload.language)
    except LLMTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)
        ) from exc
    except ReviewError as exc:
        # 502 Bad Gateway: *we* are fine, the upstream model we depend on
        # failed. That's more honest than 500 (a bug in our code) and tells
        # clients a retry may succeed.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
