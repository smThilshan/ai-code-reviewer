"""Domain errors raised by the review service.

The service translates every low-level failure (OpenAI SDK exceptions,
Pydantic validation errors) into one of these, so callers deal with three
meaningful cases instead of a dozen library-specific exceptions. It also
keeps HTTP out of the service layer: the router decides which status code
each error becomes.

Messages on these exceptions are written to be safe to show to API clients.
Raw upstream details (which could reveal keys, request IDs or internals) are
logged server-side instead, never put in the message.
"""


class ReviewError(Exception):
    """Base class for every failure while producing a review."""


class LLMUnavailableError(ReviewError):
    """The OpenAI API call failed (network error, auth, rate limit, 5xx)."""


class LLMTimeoutError(ReviewError):
    """The OpenAI API did not answer within the configured timeout."""


class LLMResponseError(ReviewError):
    """The API answered, but the result is unusable.

    Covers refusals, truncated output, filtered content, and output that
    fails validation against the ReviewResponse schema.
    """


class PullRequestError(Exception):
    """Base class for every failure while reviewing a GitHub pull request.

    Separate from ReviewError (which is about the LLM): these are about
    finding and reading the PR. Messages are safe to show to API clients.
    """


class InvalidPullRequestURLError(PullRequestError):
    """The submitted string is not a github.com pull request URL."""


class PullRequestNotFoundError(PullRequestError):
    """GitHub says the PR doesn't exist or isn't visible to us.

    GitHub deliberately answers 404 (not 403) for private repos you can't
    access, so that it doesn't reveal which private repos exist. From here,
    "doesn't exist" and "private, no access" are indistinguishable, so the
    message has to cover both.
    """


class GitHubAccessDeniedError(PullRequestError):
    """GitHub refused access (403) for a reason other than rate limiting."""


class GitHubRateLimitError(PullRequestError):
    """GitHub's API rate limit is exhausted."""


class PullRequestTooLargeError(PullRequestError):
    """The PR's diff is too large for GitHub to return."""


class NoReviewableChangesError(PullRequestError):
    """The PR changes no files we can review (docs only, deletions only, ...)."""


class GitHubTimeoutError(PullRequestError):
    """GitHub did not answer within the configured timeout."""


class GitHubUnavailableError(PullRequestError):
    """The GitHub API call failed (network error, 5xx, unexpected response)."""
