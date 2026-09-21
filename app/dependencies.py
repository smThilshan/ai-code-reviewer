"""Shared FastAPI dependencies (things routes need, built once and injected).

Routes declare `service: ReviewService = Depends(get_review_service)` instead
of constructing the service themselves. Two payoffs: routes stay free of
wiring code, and tests can swap in a fake via
`app.dependency_overrides[get_review_service]` without touching OpenAI.
"""

from functools import lru_cache

import httpx
from openai import AsyncOpenAI

from app.config import settings
from app.services.github_client import GitHubClient
from app.services.pr_review_service import PullRequestReviewService
from app.services.review_service import ReviewService


@lru_cache
def get_review_service() -> ReviewService:
    """Build the ReviewService once and reuse it for every request.

    `lru_cache` makes this a singleton. That matters because AsyncOpenAI
    owns an HTTP connection pool; creating a client per request would throw
    away connection reuse and add latency to every call.
    """
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )
    return ReviewService(client=client, model=settings.openai_model)


@lru_cache
def get_github_client() -> GitHubClient:
    """Build the GitHub client once, with our auth and identification headers."""
    headers = {
        # GitHub rejects requests without a User-Agent.
        "User-Agent": "ai-code-reviewer",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    http = httpx.AsyncClient(
        base_url="https://api.github.com",
        headers=headers,
        timeout=settings.github_timeout_seconds,
        # The API host may redirect (e.g. a renamed repo). httpx drops the
        # Authorization header if a redirect ever leaves the original host.
        follow_redirects=True,
    )
    return GitHubClient(http)


@lru_cache
def get_pull_request_review_service() -> PullRequestReviewService:
    """Compose the PR use case from the shared GitHub client and ReviewService."""
    return PullRequestReviewService(
        github=get_github_client(), reviewer=get_review_service()
    )
