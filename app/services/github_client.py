"""Talk to GitHub: parse a PR URL, fetch that PR's diff.

Only this module knows GitHub's HTTP details (endpoints, headers, which status
code means what). The rest of the app sees a `PullRequestRef` going in, diff
text coming out, and domain errors (see exceptions.py) when things go wrong.
"""

import logging
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from app.services.exceptions import (
    GitHubAccessDeniedError,
    GitHubRateLimitError,
    GitHubTimeoutError,
    GitHubUnavailableError,
    InvalidPullRequestURLError,
    PullRequestNotFoundError,
    PullRequestTooLargeError,
)

logger = logging.getLogger(__name__)

_GITHUB_HOSTS = {"github.com", "www.github.com"}
# GitHub account names: letters, digits, hyphens. Repo names also allow "." and "_".
_OWNER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
_REPO = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_PR_NUMBER = re.compile(r"^[0-9]{1,9}$")  # ASCII digits only

_EXPECTED_FORM = "https://github.com/<owner>/<repo>/pull/<number>"


@dataclass(frozen=True, slots=True)
class PullRequestRef:
    """Identifies one pull request."""

    owner: str
    repo: str
    number: int

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}/pull/{self.number}"


def parse_pull_request_url(url: str) -> PullRequestRef:
    """Extract owner, repo and PR number from a github.com pull request URL.

    Security note: we never fetch the URL the user gave us. We pull three
    validated pieces out of it and build the GitHub API URL ourselves, against
    a fixed host. If we fetched user-supplied URLs, callers could point the
    server at internal addresses (SSRF). The strict character checks below
    also keep path tricks like "owner/../x" out of that built URL.
    """
    invalid = InvalidPullRequestURLError(
        f"Not a valid GitHub pull request URL. Expected the form {_EXPECTED_FORM}."
    )

    try:
        parts = urlsplit(url.strip())
        host, port = parts.hostname, parts.port
    except ValueError as exc:  # malformed URL, e.g. a bad port or bracket
        raise invalid from exc

    if parts.scheme not in {"http", "https"} or host not in _GITHUB_HOSTS or port is not None:
        raise invalid

    # Path is /owner/repo/pull/123, optionally followed by /files, /commits, ...
    segments = [segment for segment in parts.path.split("/") if segment]
    if len(segments) < 4 or segments[2] != "pull":
        raise invalid

    owner, repo, number = segments[0], segments[1], segments[3]
    if (
        not _OWNER.fullmatch(owner)
        or not _REPO.fullmatch(repo)
        or repo in {".", ".."}
        or not _PR_NUMBER.fullmatch(number)
        or int(number) == 0
    ):
        raise invalid

    return PullRequestRef(owner=owner, repo=repo, number=int(number))


class GitHubClient:
    """Thin async client for the parts of the GitHub REST API we use."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        # Injected so the app can share one connection pool and tests can
        # supply an httpx.MockTransport instead of hitting the network.
        # `http` is expected to have base_url, User-Agent and (optionally) an
        # Authorization header already configured. See dependencies.py.
        self._http = http

    async def fetch_pull_request_diff(self, pull_request: PullRequestRef) -> str:
        """Return the PR's full unified diff as text.

        Raises a PullRequestError subclass on any failure.
        """
        path = f"/repos/{pull_request.owner}/{pull_request.repo}/pulls/{pull_request.number}"
        try:
            # This Accept header is what makes GitHub answer with the raw
            # unified diff text instead of the usual JSON description.
            response = await self._http.get(
                path, headers={"Accept": "application/vnd.github.diff"}
            )
        # TimeoutException is a subclass of HTTPError, so it must come first.
        except httpx.TimeoutException as exc:
            logger.warning("GitHub request timed out: %s", exc)
            raise GitHubTimeoutError("GitHub did not respond in time. Try again shortly.") from exc
        except httpx.HTTPError as exc:
            logger.error("Could not reach GitHub: %s", exc)
            raise GitHubUnavailableError("Could not reach GitHub. Try again shortly.") from exc

        self._raise_for_status(response)
        return response.text

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """Translate GitHub's HTTP status codes into domain errors."""
        status = response.status_code
        if status == 200:
            return

        if status == 404:
            # GitHub returns 404, not 403, for private repos you can't see, so
            # we cannot tell "doesn't exist" from "private" and must say both.
            raise PullRequestNotFoundError(
                "Pull request not found. Check the URL; if the repository is "
                "private, this service has no access to it."
            )

        body = response.text.lower()

        if status in {403, 429}:
            # Primary limit: X-RateLimit-Remaining hits 0. Secondary (abuse)
            # limits: a 403/429 whose message mentions the rate limit.
            if (
                status == 429
                or response.headers.get("x-ratelimit-remaining") == "0"
                or "rate limit" in body
            ):
                logger.warning("GitHub rate limit hit (HTTP %s)", status)
                raise GitHubRateLimitError(
                    "GitHub's API rate limit has been reached. Try again later."
                )
            raise GitHubAccessDeniedError("GitHub denied access to this pull request.")

        # GitHub answers 406 (documented) when the diff is too big to return.
        if status == 406 or (status == 422 and "too_large" in body):
            raise PullRequestTooLargeError(
                "This pull request's diff is too large for GitHub to return. "
                "Try a smaller pull request."
            )

        # 401 means OUR token is bad: nothing the caller can fix, so log it for
        # us and give them a generic message. Same for 5xx and anything else.
        logger.error("Unexpected GitHub response: HTTP %s: %s", status, response.text[:200])
        raise GitHubUnavailableError("GitHub returned an error. Try again shortly.")
