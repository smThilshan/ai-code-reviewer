"""Tests for POST /review at the HTTP level, with the service faked out.

These check the router's own jobs: input validation (422), success shape
(200), and mapping domain errors to status codes (502/504). The service is
replaced via FastAPI's dependency_overrides, so nothing touches OpenAI.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.dependencies import get_review_service
from app.main import app
from app.rate_limit import limiter
from app.schemas.examples import REVIEW_REQUEST_EXAMPLES
from app.schemas.review import MAX_CODE_CHARS, ReviewIssue, ReviewResponse
from app.services.exceptions import (
    LLMResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
)

CANNED_REVIEW = ReviewResponse(
    issues=[
        ReviewIssue(
            severity="high",
            category="bug",
            line_number=None,
            description="Whole-file problem.",
            suggested_fix="Rewrite it.",
        )
    ],
    summary="Needs work.",
)

VALID_BODY = {"code": "x = 1", "language": "python"}


class FakeService:
    """Stands in for ReviewService: returns a canned review or raises."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, str]] = []

    async def review_code(self, code: str, language: str) -> ReviewResponse:
        self.calls.append({"code": code, "language": language})
        if self.error:
            raise self.error
        return CANNED_REVIEW


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def use_service(service: FakeService) -> None:
    app.dependency_overrides[get_review_service] = lambda: service


# --- Success ----------------------------------------------------------------


def test_valid_request_returns_200_with_review_json(client: TestClient) -> None:
    use_service(FakeService())

    response = client.post("/review", json=VALID_BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "Needs work."
    assert body["issues"][0]["severity"] == "high"
    assert body["issues"][0]["line_number"] is None


def test_code_reaches_the_service_unmodified(client: TestClient) -> None:
    """Leading indentation and trailing newline must survive; only `language` is trimmed."""
    service = FakeService()
    use_service(service)
    code = "    indented_first_line()\n"

    client.post("/review", json={"code": code, "language": "  python  "})

    assert service.calls == [{"code": code, "language": "python"}]


# --- Input validation -------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"code": "", "language": "python"},
        {"code": "   \n\t ", "language": "python"},
        {"code": "x = 1", "language": ""},
        {"code": "x = 1", "language": "   "},
        {"code": "x = 1"},
        {"language": "python"},
        {"code": "x = 1", "language": "python", "extra": "nope"},
        {"code": "x" * (MAX_CODE_CHARS + 1), "language": "python"},
        {"code": 123, "language": "python"},
    ],
    ids=[
        "empty-code",
        "whitespace-code",
        "empty-language",
        "whitespace-language",
        "missing-language",
        "missing-code",
        "unknown-field",
        "code-too-long",
        "code-not-a-string",
    ],
)
def test_invalid_request_returns_422_without_calling_the_service(
    client: TestClient, body: dict
) -> None:
    service = FakeService()
    use_service(service)

    response = client.post("/review", json=body)

    assert response.status_code == 422
    assert service.calls == []


def test_code_at_exactly_the_limit_is_accepted(client: TestClient) -> None:
    use_service(FakeService())

    response = client.post("/review", json={"code": "x" * MAX_CODE_CHARS, "language": "python"})

    assert response.status_code == 200


# --- Error mapping ----------------------------------------------------------


def test_timeout_maps_to_504_with_safe_message(client: TestClient) -> None:
    use_service(FakeService(error=LLMTimeoutError("The review timed out.")))

    response = client.post("/review", json=VALID_BODY)

    assert response.status_code == 504
    assert response.json() == {"detail": "The review timed out."}


@pytest.mark.parametrize("error_type", [LLMUnavailableError, LLMResponseError])
def test_other_review_errors_map_to_502(client: TestClient, error_type: type[Exception]) -> None:
    use_service(FakeService(error=error_type("Something upstream failed.")))

    response = client.post("/review", json=VALID_BODY)

    assert response.status_code == 502
    assert response.json() == {"detail": "Something upstream failed."}


# --- Docs -------------------------------------------------------------------


def test_openapi_lists_the_example_requests(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    content = schema["paths"]["/review"]["post"]["requestBody"]["content"]["application/json"]

    assert set(content["examples"]) == set(REVIEW_REQUEST_EXAMPLES)


def test_health_endpoint_still_works(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


# --- Rate limiting ----------------------------------------------------------


def test_review_is_rate_limited_per_ip_after_the_configured_count(client: TestClient) -> None:
    use_service(FakeService())
    limiter.enabled = True
    allowed = int(settings.review_rate_limit.split("/")[0])

    statuses = [client.post("/review", json=VALID_BODY).status_code for _ in range(allowed + 1)]

    assert statuses[:allowed] == [200] * allowed
    assert statuses[allowed] == 429


def test_rate_limit_response_uses_the_apis_detail_shape(client: TestClient) -> None:
    use_service(FakeService())
    limiter.enabled = True
    for _ in range(int(settings.review_rate_limit.split("/")[0])):
        client.post("/review", json=VALID_BODY)

    response = client.post("/review", json=VALID_BODY)

    assert response.status_code == 429
    assert response.json()["detail"].startswith("Rate limit exceeded")


def test_invalid_requests_do_not_consume_the_rate_limit(client: TestClient) -> None:
    """422s are rejected before the handler runs, so they cost nothing to serve."""
    use_service(FakeService())
    limiter.enabled = True
    allowed = int(settings.review_rate_limit.split("/")[0])

    for _ in range(allowed + 5):
        assert client.post("/review", json={"code": "", "language": "python"}).status_code == 422

    assert client.post("/review", json=VALID_BODY).status_code == 200


def test_health_is_never_rate_limited(client: TestClient) -> None:
    limiter.enabled = True

    assert all(client.get("/health").status_code == 200 for _ in range(50))
