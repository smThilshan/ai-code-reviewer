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


# A single shared instance, imported wherever settings are needed:
#   from app.config import settings
settings = Settings()
