"""Tests for PR URL parsing and the GitHub client (fake transport, no network)."""

import asyncio
from collections.abc import Callable

import httpx
import pytest

from app.services.exceptions import (
    GitHubAccessDeniedError,
    GitHubRateLimitError,
    GitHubTimeoutError,
    GitHubUnavailableError,
    InvalidPullRequestURLError,
    PullRequestNotFoundError,
    PullRequestTooLargeError,
)
from app.services.github_client import GitHubClient, PullRequestRef, parse_pull_request_url

# --- URL parsing ------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/pallets/click/pull/3493",
        "https://github.com/pallets/click/pull/3493/",
        "https://github.com/pallets/click/pull/3493/files",
        "https://github.com/pallets/click/pull/3493/commits/abc123",
        "https://github.com/pallets/click/pull/3493?diff=split#discussion_r1",
        "http://github.com/pallets/click/pull/3493",
        "https://www.github.com/pallets/click/pull/3493",
        "https://GitHub.com/pallets/click/pull/3493",
        "  https://github.com/pallets/click/pull/3493  ",
    ],
)
def test_valid_pull_request_urls_are_parsed(url: str) -> None:
    assert parse_pull_request_url(url) == PullRequestRef("pallets", "click", 3493)


def test_repo_names_may_contain_dots_underscores_and_hyphens() -> None:
    ref = parse_pull_request_url("https://github.com/some-org/my_repo.js-x/pull/7")

    assert (ref.owner, ref.repo, ref.number) == ("some-org", "my_repo.js-x", 7)


def test_canonical_url_is_rebuilt_from_the_parsed_parts() -> None:
    ref = parse_pull_request_url("http://www.github.com/pallets/click/pull/3493/files?x=1")

    assert ref.url == "https://github.com/pallets/click/pull/3493"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "not a url",
        "github.com/pallets/click/pull/3493",  # no scheme
        "ftp://github.com/pallets/click/pull/3493",
        "javascript:alert(1)",
        "https://example.com/pallets/click/pull/3493",  # wrong host
        "https://github.com.evil.com/pallets/click/pull/3493",  # lookalike host
        "https://evil.com/github.com/pallets/click/pull/3493",
        "https://github.com@evil.com/pallets/click/pull/3493",  # userinfo trick
        "https://github.com:8080/pallets/click/pull/3493",
        "https://api.github.com/repos/pallets/click/pulls/3493",  # API URL, not a PR page
        "https://github.com/pallets/click",  # repo, not a PR
        "https://github.com/pallets/click/issues/3493",  # issue, not a PR
        "https://github.com/pallets/click/pull/",  # no number
        "https://github.com/pallets/click/pull/abc",
        "https://github.com/pallets/click/pull/0",
        "https://github.com/pallets/click/pull/-5",
        "https://github.com/pallets/click/pull/1234567890",  # too many digits
        "https://github.com/pallets/click/pull/٣٤",  # non-ASCII digits
        "https://github.com/pallets/../pull/1",  # path traversal in repo slot
        "https://github.com/../click/pull/1",
        "https://github.com/pal_lets/click/pull/1",  # underscore not allowed in owner
        "https://github.com/-pallets/click/pull/1",
        "https://github.com/pallets/cl ick/pull/1",
        "https://github.com/pallets/click%2Fx/pull/1",
    ],
)
def test_invalid_pull_request_urls_are_rejected(url: str) -> None:
    with pytest.raises(InvalidPullRequestURLError):
        parse_pull_request_url(url)


def test_invalid_url_message_says_what_a_valid_one_looks_like() -> None:
    with pytest.raises(InvalidPullRequestURLError, match=r"github\.com/<owner>/<repo>/pull/<number>"):
        parse_pull_request_url("nope")


# --- Fetching the diff ------------------------------------------------------

PR = PullRequestRef("pallets", "click", 3493)
Handler = Callable[[httpx.Request], httpx.Response]


def make_client(handler: Handler) -> GitHubClient:
    http = httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(handler)
    )
    return GitHubClient(http)


def fetch(client: GitHubClient) -> str:
    return asyncio.run(client.fetch_pull_request_diff(PR))


def test_success_returns_the_diff_text_and_asks_for_the_diff_media_type() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="diff --git a/x b/x\n")

    assert fetch(make_client(handler)) == "diff --git a/x b/x\n"
    assert str(seen[0].url) == "https://api.github.com/repos/pallets/click/pulls/3493"
    assert seen[0].headers["accept"] == "application/vnd.github.diff"


def test_utf8_diff_content_is_decoded_correctly() -> None:
    body = "+café ☃\n".encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-type": "text/plain"})

    assert fetch(make_client(handler)) == "+café ☃\n"


def test_404_means_not_found_or_private() -> None:
    client = make_client(lambda request: httpx.Response(404, json={"message": "Not Found"}))

    with pytest.raises(PullRequestNotFoundError, match="private"):
        fetch(client)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, json={"message": "x"}),
        httpx.Response(429, json={"message": "x"}),
        httpx.Response(403, json={"message": "You have exceeded a secondary rate limit."}),
    ],
    ids=["primary-limit", "429", "secondary-limit"],
)
def test_rate_limiting_is_recognised(response: httpx.Response) -> None:
    with pytest.raises(GitHubRateLimitError):
        fetch(make_client(lambda request: response))


def test_other_403_means_access_denied() -> None:
    client = make_client(
        lambda request: httpx.Response(
            403, headers={"x-ratelimit-remaining": "42"}, json={"message": "Resource not accessible"}
        )
    )

    with pytest.raises(GitHubAccessDeniedError):
        fetch(client)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(406, json={"message": "Sorry, the diff exceeded the maximum number of lines"}),
        httpx.Response(422, json={"errors": [{"field": "diff", "code": "too_large"}]}),
    ],
    ids=["406", "422-too_large"],
)
def test_oversized_diff_is_recognised(response: httpx.Response) -> None:
    with pytest.raises(PullRequestTooLargeError):
        fetch(make_client(lambda request: response))


@pytest.mark.parametrize("status", [401, 500, 502, 503, 418])
def test_other_statuses_become_unavailable_without_leaking_details(status: int) -> None:
    client = make_client(
        lambda request: httpx.Response(status, json={"message": "Bad credentials ghp_secret123"})
    )

    with pytest.raises(GitHubUnavailableError) as exc_info:
        fetch(client)

    assert "ghp_secret123" not in str(exc_info.value)
    assert "Bad credentials" not in str(exc_info.value)


def test_timeout_becomes_github_timeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(GitHubTimeoutError):
        fetch(make_client(handler))


def test_connection_failure_becomes_github_unavailable_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(GitHubUnavailableError):
        fetch(make_client(handler))
