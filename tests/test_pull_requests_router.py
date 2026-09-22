"""Tests for POST /review-pr at the HTTP level, with the service faked out."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.dependencies import get_pull_request_review_service, get_review_service
from app.main import app
from app.rate_limit import limiter
from app.schemas.examples import PR_REVIEW_REQUEST_EXAMPLES
from app.schemas.pull_request import FileReview, PullRequestReviewResponse, SkippedFile
from app.schemas.review import Category, ReviewIssue, ReviewResponse, Severity
from app.services.exceptions import (
    GitHubAccessDeniedError,
    GitHubRateLimitError,
    GitHubTimeoutError,
    GitHubUnavailableError,
    InvalidPullRequestURLError,
    LLMResponseError,
    LLMTimeoutError,
    NoReviewableChangesError,
    PullRequestNotFoundError,
    PullRequestTooLargeError,
)

BODY = {"pr_url": "https://github.com/pallets/click/pull/3493"}

CANNED = PullRequestReviewResponse(
    pull_request="https://github.com/pallets/click/pull/3493",
    files=[
        FileReview(
            path="src/click/utils.py",
            language="python",
            lines_reviewed=4,
            review=ReviewResponse(
                issues=[
                    ReviewIssue(
                        severity=Severity.MEDIUM,
                        category=Category.BUG,
                        line_number=212,
                        description="d",
                        suggested_fix="f",
                    )
                ],
                summary="s",
            ),
            error=None,
        )
    ],
    skipped_files=[SkippedFile(path="CHANGES.rst", reason="not a recognized source-code file type")],
)


class FakePRService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[str] = []

    async def review_pull_request(self, pr_url: str) -> PullRequestReviewResponse:
        self.calls.append(pr_url)
        if self.error:
            raise self.error
        return CANNED


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def use_service(service: FakePRService) -> None:
    app.dependency_overrides[get_pull_request_review_service] = lambda: service


def test_success_returns_files_and_skipped_files(client: TestClient) -> None:
    use_service(FakePRService())

    response = client.post("/review-pr", json=BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["pull_request"] == BODY["pr_url"]
    assert body["files"][0]["path"] == "src/click/utils.py"
    assert body["files"][0]["review"]["issues"][0]["line_number"] == 212
    assert body["skipped_files"] == [
        {"path": "CHANGES.rst", "reason": "not a recognized source-code file type"}
    ]


def test_url_is_passed_to_the_service_with_surrounding_whitespace_trimmed(client: TestClient) -> None:
    service = FakePRService()
    use_service(service)

    client.post("/review-pr", json={"pr_url": f"  {BODY['pr_url']}  "})

    assert service.calls == [BODY["pr_url"]]


@pytest.mark.parametrize(
    "body",
    [{}, {"pr_url": ""}, {"pr_url": "   "}, {"pr_url": 5}, {"pr_url": "x" * 301}, {**BODY, "extra": 1}],
    ids=["missing", "empty", "blank", "not-a-string", "too-long", "unknown-field"],
)
def test_malformed_requests_get_422_without_calling_the_service(client: TestClient, body: dict) -> None:
    service = FakePRService()
    use_service(service)

    assert client.post("/review-pr", json=body).status_code == 422
    assert service.calls == []


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (InvalidPullRequestURLError("bad url"), 422),
        (NoReviewableChangesError("only docs"), 422),
        (PullRequestTooLargeError("too big"), 422),
        (PullRequestNotFoundError("missing or private"), 404),
        (GitHubAccessDeniedError("denied"), 403),
        (GitHubRateLimitError("github limit"), 503),
        (GitHubTimeoutError("github slow"), 504),
        (LLMTimeoutError("model slow"), 504),
        (GitHubUnavailableError("github down"), 502),
        (LLMResponseError("model junk"), 502),
    ],
    ids=lambda value: type(value).__name__ if isinstance(value, Exception) else str(value),
)
def test_domain_errors_map_to_http_statuses_with_their_message(
    client: TestClient, error: Exception, expected_status: int
) -> None:
    use_service(FakePRService(error=error))

    response = client.post("/review-pr", json=BODY)

    assert response.status_code == expected_status
    assert response.json() == {"detail": str(error)}


def test_review_pr_has_its_own_tighter_rate_limit(client: TestClient) -> None:
    use_service(FakePRService())
    limiter.enabled = True
    allowed = int(settings.review_pr_rate_limit.split("/")[0])

    statuses = [client.post("/review-pr", json=BODY).status_code for _ in range(allowed + 1)]

    assert statuses == [200] * allowed + [429]
    assert allowed < int(settings.review_rate_limit.split("/")[0])  # PRs cost more, so fewer


def test_review_and_review_pr_have_independent_rate_limit_counters(client: TestClient) -> None:
    class OkReviewService:
        async def review_code(
            self, code: str, language: str | None = None, filename: str | None = None
        ) -> ReviewResponse:
            return ReviewResponse(issues=[], summary="fine")

    use_service(FakePRService())
    app.dependency_overrides[get_review_service] = lambda: OkReviewService()
    limiter.enabled = True
    for _ in range(int(settings.review_pr_rate_limit.split("/")[0])):
        client.post("/review-pr", json=BODY)
    assert client.post("/review-pr", json=BODY).status_code == 429

    response = client.post("/review", json={"code": "x = 1", "language": "python"})

    assert response.status_code == 200


def test_openapi_lists_the_pr_examples(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    content = schema["paths"]["/review-pr"]["post"]["requestBody"]["content"]["application/json"]

    assert set(content["examples"]) == set(PR_REVIEW_REQUEST_EXAMPLES)
