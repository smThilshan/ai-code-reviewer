"""Shared test setup.

`app.config` refuses to import without OPENAI_API_KEY (by design, see
Phase 1). Tests never call OpenAI (they use fakes), but importing the app
still runs that check, so we provide a dummy key *before* any test module
imports the app. `setdefault` leaves a real key alone if one is set.
"""

import os

os.environ.setdefault("OPENAI_API_KEY", "test-key-not-used")

import pytest  # noqa: E402  (must come after the env var above is set)

from app.rate_limit import limiter  # noqa: E402


@pytest.fixture(autouse=True)
def _rate_limiting_off_by_default():
    """Disable the limiter for every test, and restore it afterwards.

    Its counters live in process memory and are shared by every test, so
    without this, tests that happen to run close together would start
    getting 429s from each other. Rate-limit tests turn it back on explicitly.
    """
    limiter.enabled = False
    limiter.reset()
    yield
    limiter.enabled = True
    limiter.reset()
