"""The pull-request review use case.

Pipeline: parse URL -> fetch diff from GitHub -> parse diff into per-file added
lines -> decide which files are worth reviewing -> review each with the
EXISTING ReviewService -> assemble the result.

This class owns only the PR-specific orchestration. All LLM logic (prompt,
structured output, validation, error handling, line-number checking) stays in
ReviewService and is reused as-is, so a fix there improves both endpoints.
"""

import asyncio
import logging

from app.schemas.pull_request import ExcerptLine, FileReview, PullRequestReviewResponse, SkippedFile
from app.schemas.review import MAX_CODE_CHARS
from app.services.diff_parser import FileDiff, parse_diff
from app.services.exceptions import NoReviewableChangesError, ReviewError
from app.services.github_client import GitHubClient, parse_pull_request_url
from app.services.languages import language_for_path
from app.services.review_service import ReviewService

logger = logging.getLogger(__name__)

# Every reviewed file is one paid model call. Capping files per PR bounds the
# worst-case cost of a single request; the rest are reported as skipped, not
# silently dropped.
MAX_FILES_PER_PR = 10

# How many model calls run at once for one PR. Parallel is much faster than one
# by one (10 files ~ 3 rounds instead of 10), but unbounded parallelism invites
# OpenAI rate limits and multiplies the load one request can create.
MAX_CONCURRENT_REVIEWS = 3

# How many skipped files to name in the "nothing reviewable" error message.
_MAX_NAMED_IN_ERROR = 5


class PullRequestReviewService:
    """Reviews the code a GitHub pull request adds or changes."""

    def __init__(self, github: GitHubClient, reviewer: ReviewService) -> None:
        self._github = github
        self._reviewer = reviewer

    async def review_pull_request(self, pr_url: str) -> PullRequestReviewResponse:
        """Review a pull request, given its github.com URL.

        Raises:
            PullRequestError: the URL is invalid, GitHub couldn't supply the
                diff, or the PR has nothing reviewable.
            ReviewError: the model failed for EVERY file (a systemic failure,
                such as a bad API key). If only some files fail, the request
                succeeds and those files carry an `error` instead.
        """
        pull_request = parse_pull_request_url(pr_url)
        diff_text = await self._github.fetch_pull_request_diff(pull_request)

        reviewable, skipped = self._select_files(parse_diff(diff_text))
        if not reviewable:
            raise NoReviewableChangesError(self._no_changes_message(skipped))

        outcomes = await self._review_all(reviewable)

        # If every file failed, the problem isn't one file; report it as the
        # failure it is instead of a 200 whose every entry is an error.
        if all(error is not None for _, error in outcomes):
            raise outcomes[0][1]  # type: ignore[misc]

        return PullRequestReviewResponse(
            pull_request=pull_request.url,
            files=[file_review for file_review, _ in outcomes],
            skipped_files=skipped,
        )

    @staticmethod
    def _select_files(files: list[FileDiff]) -> tuple[list[FileDiff], list[SkippedFile]]:
        """Split the diff's files into "worth reviewing" and "skipped, with why"."""
        reviewable: list[FileDiff] = []
        skipped: list[SkippedFile] = []

        for file in files:
            reason = PullRequestReviewService._skip_reason(file)
            if reason is None and len(reviewable) >= MAX_FILES_PER_PR:
                reason = f"over the limit of {MAX_FILES_PER_PR} files reviewed per pull request"

            if reason is None:
                reviewable.append(file)
            else:
                skipped.append(SkippedFile(path=file.path, reason=reason))

        return reviewable, skipped

    @staticmethod
    def _skip_reason(file: FileDiff) -> str | None:
        """Why this file shouldn't be reviewed, or None if it should be."""
        if file.is_deleted:
            return "file was deleted"
        if file.is_binary:
            return "binary file"
        if language_for_path(file.path) is None:
            return "not a recognized source-code file type"
        if not file.added_lines:
            return "no added or changed lines (only removals, a rename or a mode change)"
        # Measured on everything sent to the model, context included.
        if sum(len(line.text) + 1 for line in file.lines) > MAX_CODE_CHARS:
            return f"changes too large to review (over {MAX_CODE_CHARS:,} characters)"
        return None

    async def _review_all(
        self, files: list[FileDiff]
    ) -> list[tuple[FileReview, ReviewError | None]]:
        """Review files concurrently (bounded), keeping the diff's file order."""
        # Created here, not in __init__: asyncio primitives belong to one
        # event loop, and this object lives across many requests.
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REVIEWS)
        return list(await asyncio.gather(*(self._review_one(f, semaphore) for f in files)))

    async def _review_one(
        self, file: FileDiff, semaphore: asyncio.Semaphore
    ) -> tuple[FileReview, ReviewError | None]:
        """Review one file's added lines; a model failure is captured, not raised.

        Capturing it means one flaky file doesn't throw away the reviews of
        the others (gather would otherwise propagate the first exception).
        """
        language = language_for_path(file.path) or "text"
        # Exposed as-is to the frontend (see FileReview.excerpt's docstring) so
        # it can show a code preview without fetching or storing whole files.
        # Kept on both the success AND failure path below: even a file whose
        # review failed still has real lines worth showing.
        excerpt = [
            ExcerptLine(line_number=line.number, text=line.text, is_context=line.context)
            for line in file.lines
        ]
        base = {
            "path": file.path,
            "language": language,
            "lines_reviewed": len(file.added_lines),
            "excerpt": excerpt,
        }

        async with semaphore:
            try:
                # Every line carries its REAL line number, so the model reads and
                # reports true file line numbers directly, with no translation
                # step to get wrong. The lines include unchanged context
                # (flagged read-only) so the model can see how the changed code
                # fits in; ReviewService then guarantees it only reports issues
                # on the added lines. `excerpt=True` tells the model it is
                # seeing part of a file.
                review = await self._reviewer.review_lines(
                    file.lines, language, excerpt=True
                )
            except ReviewError as exc:
                logger.warning("Review of %s failed: %s", file.path, exc)
                return FileReview(**base, review=None, error=str(exc)), exc

        return FileReview(**base, review=review, error=None), None

    @staticmethod
    def _no_changes_message(skipped: list[SkippedFile]) -> str:
        message = "This pull request has no code changes to review."
        if skipped:
            named = "; ".join(f"{s.path} ({s.reason})" for s in skipped[:_MAX_NAMED_IN_ERROR])
            more = len(skipped) - _MAX_NAMED_IN_ERROR
            suffix = f"; and {more} more" if more > 0 else ""
            message += f" Skipped: {named}{suffix}."
        return message
