"""FastAPI application entry point.

Kept intentionally minimal: this file only wires the app together
(create the FastAPI instance, mount routers). Actual endpoint logic
lives in `app/routers/`, and business logic lives in `app/services/` —
that separation is what keeps this file readable as the project grows
across the remaining phases.
"""

from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded

# Importing settings here ensures config validation (see app/config.py)
# runs at startup — if OPENAI_API_KEY is missing, the app fails to boot
# immediately with a clear error, instead of failing later mid-request.
from app.config import settings  # noqa: F401
from app.rate_limit import limiter, rate_limit_exceeded_handler
from app.routers import pull_requests, review
from app.schemas.health import HealthDetail, RateLimits

# Single source of truth for the app's version, so FastAPI's own metadata
# (shown in /docs) and the /health/detailed payload can't drift apart.
APP_VERSION = "0.1.0"

app = FastAPI(
    title="AI Code Reviewer",
    description="An AI-powered code review service.",
    version=APP_VERSION,
)

# slowapi looks the limiter up on app.state, and needs a handler to turn its
# RateLimitExceeded exception into an HTTP 429 response.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

app.include_router(review.router)
app.include_router(pull_requests.router)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Liveness check used to confirm the service is running."""
    return {"status": "ok"}


@app.get(
    "/health/detailed",
    summary="Configuration and readiness snapshot",
    tags=["health"],
)
def health_detailed() -> HealthDetail:
    """A demo/debugging view of how this instance is configured.

    Reads only local settings — it never calls OpenAI or GitHub — so it's
    safe to hit as often as a demo UI wants without costing anything or
    slowing anything down. See HealthDetail's docstring for what that means
    for `openai_configured`.
    """
    return HealthDetail(
        status="ok",
        version=APP_VERSION,
        openai_model=settings.openai_model,
        openai_configured=bool(settings.openai_api_key),
        github_token_configured=settings.github_token is not None,
        rate_limits=RateLimits(
            review=settings.review_rate_limit,
            review_pr=settings.review_pr_rate_limit,
        ),
    )
