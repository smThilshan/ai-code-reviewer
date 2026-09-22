"""Tests for GET /health/detailed."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import APP_VERSION, app
from app.rate_limit import limiter


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def test_returns_the_expected_shape_and_values(client: TestClient) -> None:
    response = client.get("/health/detailed")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": APP_VERSION,
        "openai_model": settings.openai_model,
        "openai_configured": True,  # the app couldn't have started otherwise
        "github_token_configured": settings.github_token is not None,
        "rate_limits": {
            "review": settings.review_rate_limit,
            "review_pr": settings.review_pr_rate_limit,
        },
    }


def test_github_token_configured_reflects_settings_when_a_token_is_set(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "github_token", "ghp_fake_for_test")

    assert client.get("/health/detailed").json()["github_token_configured"] is True


def test_is_never_rate_limited(client: TestClient) -> None:
    """A demo UI or load balancer may poll this often; it must never 429."""
    limiter.enabled = True

    assert all(client.get("/health/detailed").status_code == 200 for _ in range(50))


def test_does_not_call_openai_or_github(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reads local config only — no network, no dependency on a real key working."""

    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("health/detailed must not make network calls")

    import httpx
    import openai

    monkeypatch.setattr(openai.AsyncOpenAI, "__init__", boom)
    monkeypatch.setattr(httpx.AsyncClient, "get", boom)

    assert client.get("/health/detailed").status_code == 200
