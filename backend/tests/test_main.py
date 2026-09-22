"""Tests for app-level wiring in main.py: CORS.

Everything else main.py wires up (routers, rate limiter, /health) is already
covered where it's tested in depth — this file is specifically for the CORS
middleware, since nothing else exercises it.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

ALLOWED_ORIGIN = settings.cors_allowed_origins[0]  # http://localhost:5173 by default


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def test_allowed_origin_gets_the_cors_header_on_a_real_request(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": ALLOWED_ORIGIN})

    assert response.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN


def test_disallowed_origin_gets_no_cors_header(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "https://evil.example.com"})

    # The request itself isn't blocked server-side (CORS is enforced by the
    # BROWSER reading this header, not by the server refusing the request) —
    # what matters is the header's absence, which is what makes the browser
    # reject the response.
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_preflight_for_the_review_endpoint_is_approved_for_an_allowed_origin(
    client: TestClient,
) -> None:
    response = client.options(
        "/review",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN
    assert "POST" in response.headers.get("access-control-allow-methods", "")


def test_credentials_are_not_allowed() -> None:
    """Nothing in this app uses cookies/browser-stored auth — keep it that way."""
    assert settings.cors_allowed_origins  # sanity: the setting itself parsed
    with TestClient(app) as client:
        response = client.get("/health", headers={"Origin": ALLOWED_ORIGIN})
    assert "access-control-allow-credentials" not in response.headers
