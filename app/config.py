"""Application configuration, loaded from environment variables.

Centralizing config here (instead of scattering `os.getenv()` calls across
the codebase) gives us one place to see every setting the app depends on,
and lets us fail fast at startup if something required is missing — rather
than crashing later, mid-request, when a service first tries to use it.
"""

import os

from dotenv import load_dotenv

# Load variables from a local .env file into the process environment.
# This is a no-op in production if .env doesn't exist (e.g. real env vars
# are injected by the host), so it's safe to call unconditionally.
load_dotenv()


class Settings:
    """Typed access to required environment variables.

    Reading `OPENAI_API_KEY` here — once, at import time — means every
    other module can trust that `settings.openai_api_key` is a valid,
    non-empty string, instead of each one re-checking `os.getenv()` and
    handling the "what if it's None" case independently.
    """

    def __init__(self) -> None:
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise RuntimeError(
                "Missing required environment variable: OPENAI_API_KEY. "
                "Copy .env.example to .env and fill in your OpenAI API key."
            )
        self.openai_api_key: str = openai_api_key

        # Optional settings, with defaults. The model name lives here so it
        # can be swapped (e.g. to a newer model) without touching service code.
        self.openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        # Per-request timeout. The SDK also retries transient failures
        # (connection errors, 429, 5xx) up to `openai_max_retries` times, so
        # the worst-case wait is roughly timeout * (retries + 1).
        self.openai_timeout_seconds: float = 30.0
        self.openai_max_retries: int = 2

        # GitHub access for PR review (Phase 5). The token is OPTIONAL: public
        # repos work without one, but unauthenticated GitHub allows only 60
        # requests/hour per IP, so setting one is strongly advised. Treat
        # empty as unset. Use a read-only token: see .env.example for why.
        self.github_token: str | None = os.getenv("GITHUB_TOKEN") or None
        self.github_timeout_seconds: float = 15.0

        # Per-IP rate limits, in slowapi/`limits` syntax ("count/period",
        # several allowed, separated by ";"). A PR review can trigger up to
        # ~10 model calls, so it gets a much tighter limit than a single-file
        # review. Overridable so a deployment can tune them without a code
        # change.
        self.review_rate_limit: str = os.getenv("REVIEW_RATE_LIMIT", "10/minute;100/hour")
        self.review_pr_rate_limit: str = os.getenv("REVIEW_PR_RATE_LIMIT", "5/minute;30/hour")


# A single shared instance, imported wherever settings are needed:
#   from app.config import settings
settings = Settings()
