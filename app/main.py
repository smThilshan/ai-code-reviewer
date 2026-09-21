"""FastAPI application entry point.

Kept intentionally minimal: this file only wires the app together
(create the FastAPI instance, mount routers). Actual endpoint logic
lives in `app/routers/`, and business logic lives in `app/services/` —
that separation is what keeps this file readable as the project grows
across the remaining phases.
"""

from fastapi import FastAPI

# Importing settings here ensures config validation (see app/config.py)
# runs at startup — if OPENAI_API_KEY is missing, the app fails to boot
# immediately with a clear error, instead of failing later mid-request.
from app.config import settings  # noqa: F401

app = FastAPI(
    title="AI Code Reviewer",
    description="An AI-powered code review service.",
    version="0.1.0",
)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Liveness check used to confirm the service is running."""
    return {"status": "ok"}
