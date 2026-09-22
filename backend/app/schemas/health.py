"""Schema for GET /health/detailed."""

from pydantic import BaseModel, Field


class RateLimits(BaseModel):
    """The configured per-IP rate limits, in slowapi/`limits` syntax."""

    review: str = Field(description="Limit for POST /review, e.g. '10/minute;100/hour'.")
    review_pr: str = Field(description="Limit for POST /review-pr.")


class HealthDetail(BaseModel):
    """Configuration and readiness snapshot, for demos and debugging.

    Everything here comes from local config (env vars) — nothing calls
    OpenAI or GitHub. That keeps this endpoint instant and free to hit
    repeatedly (e.g. a frontend polling it, or a load balancer), unlike a
    real dependency check, which would cost money and add latency on every
    call. The trade-off: `openai_configured` means a key is PRESENT, not
    that it's valid — this endpoint can't tell a real key from a typo'd one
    without spending a request to find out.
    """

    status: str = Field(description="Always 'ok' if this endpoint could run at all.")
    version: str = Field(description="Application version.")
    openai_model: str = Field(description="Model used for reviews.")
    openai_configured: bool = Field(
        description="Whether an OpenAI API key is present. Always true once the "
        "app has started: app.config.Settings refuses to boot without one."
    )
    github_token_configured: bool = Field(
        description="Whether GITHUB_TOKEN is set. False means /review-pr works "
        "only for public repos, limited to 60 GitHub requests/hour/IP."
    )
    rate_limits: RateLimits
