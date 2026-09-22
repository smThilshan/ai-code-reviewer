"""Tests for PullRequestReviewService with a fake GitHub client and fake reviewer.

The point of these: the PR service must reuse ReviewService (not duplicate it),
hand it the real line numbers, skip what shouldn't be reviewed, and degrade
gracefully when individual files fail.
"""

import asyncio

import pytest

from app.schemas.review import MAX_CODE_CHARS, Category, ReviewIssue, ReviewResponse, Severity
from app.services.exceptions import (
    InvalidPullRequestURLError,
    LLMResponseError,
    LLMUnavailableError,
    NoReviewableChangesError,
    PullRequestNotFoundError,
)
from app.services.line_numbering import NumberedLine
from app.services.pr_review_service import (
    MAX_CONCURRENT_REVIEWS,
    MAX_FILES_PER_PR,
    PullRequestReviewService,
)

PR_URL = "https://github.com/pallets/click/pull/3493"


def file_diff(path: str, *added: tuple[int, str], start: int | None = None) -> str:
    """One file section of a diff that adds the given (number, text) lines.

    Lines are emitted as consecutive additions from the first number; enough
    for these tests, where the parser itself is already covered elsewhere.
    """
    first = start if start is not None else added[0][0]
    body = [f"+{text}" for _, text in added]
    return "\n".join(
        [
            f"diff --git a/{path} b/{path}",
            f"--- a/{path}",
            f"+++ b/{path}",
            f"@@ -{first},0 +{first},{len(added)} @@",
            *body,
            "",
        ]
    )


class FakeGitHub:
    def __init__(self, diff: str = "", error: Exception | None = None) -> None:
        self.diff = diff
        self.error = error
        self.calls = 0

    async def fetch_pull_request_diff(self, pull_request) -> str:  # noqa: ANN001
        self.calls += 1
        if self.error:
            raise self.error
        return self.diff


class FakeReviewer:
    """Records what it was asked to review; returns one canned issue per file."""

    def __init__(self, fail_on: dict[str, Exception] | None = None, delay: float = 0) -> None:
        self.calls: list[dict] = []
        self.fail_on = fail_on or {}
        self.delay = delay
        self.running = 0
        self.max_running = 0

    async def review_lines(self, lines, language, *, excerpt=False) -> ReviewResponse:  # noqa: ANN001
        first_text = lines[0].text
        self.calls.append({"lines": list(lines), "language": language, "excerpt": excerpt})

        self.running += 1
        self.max_running = max(self.max_running, self.running)
        try:
            await asyncio.sleep(self.delay)
        finally:
            self.running -= 1

        if first_text in self.fail_on:
            raise self.fail_on[first_text]
        return ReviewResponse(
            issues=[
                ReviewIssue(
                    severity=Severity.LOW,
                    category=Category.STYLE,
                    line_number=lines[0].number,
                    description=f"about {first_text}",
                    suggested_fix="fix it",
                )
            ],
            summary="ok",
        )


def review(diff: str, reviewer: FakeReviewer | None = None, github: FakeGitHub | None = None):
    reviewer = reviewer or FakeReviewer()
    github = github or FakeGitHub(diff)
    service = PullRequestReviewService(github=github, reviewer=reviewer)  # type: ignore[arg-type]
    return asyncio.run(service.review_pull_request(PR_URL))


# --- Reuse and real line numbers ---------------------------------------------


def test_reviewer_is_called_with_real_line_numbers_language_and_excerpt_flag() -> None:
    reviewer = FakeReviewer()

    review(file_diff("src/app.py", (41, "def a():"), (42, "    return 1")), reviewer)

    (call,) = reviewer.calls
    assert call["lines"] == [NumberedLine(41, "def a():"), NumberedLine(42, "    return 1")]
    assert call["language"] == "python"
    assert call["excerpt"] is True


def test_issue_line_numbers_are_the_files_real_lines() -> None:
    result = review(file_diff("src/app.py", (120, "x = 1"), (121, "y = 2")))

    (file,) = result.files
    assert file.review is not None
    assert file.review.issues[0].line_number == 120  # not 1, and not a diff position


def test_result_describes_each_file_and_the_pr() -> None:
    result = review(file_diff("src/app.py", (1, "a"), (2, "b"), (3, "c")))

    assert result.pull_request == PR_URL
    (file,) = result.files
    assert (file.path, file.language, file.lines_reviewed, file.error) == ("src/app.py", "python", 3, None)
    assert result.skipped_files == []


def test_language_is_inferred_per_file() -> None:
    reviewer = FakeReviewer()
    diff = file_diff("a.py", (1, "py")) + file_diff("b.ts", (1, "ts")) + file_diff("c.go", (1, "go"))

    review(diff, reviewer)

    assert [c["language"] for c in reviewer.calls] == ["python", "typescript", "go"]


def test_files_come_back_in_diff_order() -> None:
    diff = file_diff("z.py", (1, "z")) + file_diff("a.py", (1, "a")) + file_diff("m.py", (1, "m"))

    result = review(diff, FakeReviewer(delay=0.01))

    assert [f.path for f in result.files] == ["z.py", "a.py", "m.py"]


# --- Skipping ---------------------------------------------------------------


def skipped(result) -> dict[str, str]:  # noqa: ANN001
    return {s.path: s.reason for s in result.skipped_files}


def test_non_code_files_are_skipped_with_a_reason_while_code_is_still_reviewed() -> None:
    diff = (
        file_diff("README.md", (1, "# hi"))
        + file_diff("src/app.py", (1, "x = 1"))
        + file_diff("CHANGES.rst", (1, "notes"))
        + file_diff("package-lock.json", (1, "{}"))
    )

    result = review(diff)

    assert [f.path for f in result.files] == ["src/app.py"]
    assert set(skipped(result)) == {"README.md", "CHANGES.rst", "package-lock.json"}
    assert "source-code" in skipped(result)["README.md"]


def test_deleted_binary_and_rename_only_files_are_skipped_with_specific_reasons() -> None:
    diff = "\n".join(
        [
            "diff --git a/gone.py b/gone.py",
            "deleted file mode 100644",
            "--- a/gone.py",
            "+++ /dev/null",
            "@@ -1,1 +0,0 @@",
            "-bye",
            "diff --git a/logo.py b/logo.py",  # binary despite a code extension
            "Binary files a/logo.py and b/logo.py differ",
            "diff --git a/old.py b/new.py",
            "rename from old.py",
            "rename to new.py",
            "",
        ]
    ) + file_diff("keep.py", (1, "x = 1"))

    result = review(diff)

    assert [f.path for f in result.files] == ["keep.py"]
    reasons = skipped(result)
    assert "deleted" in reasons["gone.py"]
    assert "binary" in reasons["logo.py"]
    assert "no added" in reasons["new.py"]


def test_file_with_too_many_changed_characters_is_skipped_not_truncated() -> None:
    huge = "x" * (MAX_CODE_CHARS + 1)
    diff = file_diff("big.py", (1, huge)) + file_diff("small.py", (1, "y = 1"))

    result = review(diff)

    assert [f.path for f in result.files] == ["small.py"]
    assert "too large" in skipped(result)["big.py"]


def test_only_the_first_max_files_are_reviewed_and_the_rest_are_reported() -> None:
    total = MAX_FILES_PER_PR + 2
    diff = "".join(file_diff(f"f{i:02}.py", (1, f"x{i}")) for i in range(total))
    reviewer = FakeReviewer()

    result = review(diff, reviewer)

    assert len(result.files) == MAX_FILES_PER_PR
    assert len(reviewer.calls) == MAX_FILES_PER_PR
    assert set(skipped(result)) == {"f10.py", "f11.py"}
    assert "limit" in skipped(result)["f10.py"]


def test_files_skipped_for_other_reasons_do_not_use_up_the_file_limit() -> None:
    diff = "".join(file_diff(f"doc{i}.md", (1, "d")) for i in range(MAX_FILES_PER_PR)) + file_diff(
        "real.py", (1, "x = 1")
    )

    result = review(diff)

    assert [f.path for f in result.files] == ["real.py"]


# --- Nothing to review -------------------------------------------------------


def test_pr_with_only_docs_raises_and_names_the_skipped_files() -> None:
    diff = file_diff("README.md", (1, "# title")) + file_diff("docs/guide.rst", (1, "text"))

    with pytest.raises(NoReviewableChangesError) as exc_info:
        review(diff)

    message = str(exc_info.value)
    assert "README.md" in message
    assert "docs/guide.rst" in message


def test_empty_diff_raises_no_reviewable_changes() -> None:
    with pytest.raises(NoReviewableChangesError):
        review("")


def test_nothing_reviewable_never_calls_the_model() -> None:
    reviewer = FakeReviewer()

    with pytest.raises(NoReviewableChangesError):
        review(file_diff("README.md", (1, "x")), reviewer)

    assert reviewer.calls == []


def test_long_skip_list_in_the_error_is_abbreviated() -> None:
    diff = "".join(file_diff(f"n{i}.md", (1, "x")) for i in range(9))

    with pytest.raises(NoReviewableChangesError, match="and 4 more"):
        review(diff)


# --- Errors ------------------------------------------------------------------


def test_invalid_url_fails_before_any_github_call() -> None:
    github = FakeGitHub()
    service = PullRequestReviewService(github=github, reviewer=FakeReviewer())  # type: ignore[arg-type]

    with pytest.raises(InvalidPullRequestURLError):
        asyncio.run(service.review_pull_request("https://example.com/not/a/pr"))

    assert github.calls == 0


def test_github_errors_propagate_unchanged() -> None:
    github = FakeGitHub(error=PullRequestNotFoundError("nope"))

    with pytest.raises(PullRequestNotFoundError):
        review("", github=github)


def test_one_failing_file_does_not_fail_the_whole_review() -> None:
    reviewer = FakeReviewer(fail_on={"BAD": LLMResponseError("model returned junk")})
    diff = file_diff("a.py", (1, "ok1")) + file_diff("b.py", (1, "BAD")) + file_diff("c.py", (1, "ok2"))

    result = review(diff, reviewer)

    by_path = {f.path: f for f in result.files}
    assert by_path["a.py"].review is not None and by_path["a.py"].error is None
    assert by_path["b.py"].review is None
    assert by_path["b.py"].error == "model returned junk"
    assert by_path["c.py"].review is not None


def test_if_every_file_fails_the_first_error_is_raised() -> None:
    reviewer = FakeReviewer(
        fail_on={"one": LLMUnavailableError("first"), "two": LLMResponseError("second")}
    )
    diff = file_diff("a.py", (1, "one")) + file_diff("b.py", (1, "two"))

    with pytest.raises(LLMUnavailableError, match="first"):
        review(diff, reviewer)


# --- Concurrency -------------------------------------------------------------


def test_reviews_run_in_parallel_but_never_exceed_the_concurrency_cap() -> None:
    reviewer = FakeReviewer(delay=0.02)
    diff = "".join(file_diff(f"f{i}.py", (1, f"x{i}")) for i in range(8))

    review(diff, reviewer)

    assert 1 < reviewer.max_running <= MAX_CONCURRENT_REVIEWS


# --- Context lines -------------------------------------------------------------

DIFF_WITH_CONTEXT = "\n".join(
    [
        "diff --git a/src/app.py b/src/app.py",
        "--- a/src/app.py",
        "+++ b/src/app.py",
        "@@ -40,3 +40,4 @@",
        " before",
        "-old",
        "+new_a",
        "+new_b",
        " after",
        "",
    ]
)


def test_reviewer_receives_context_lines_flagged_alongside_the_added_ones() -> None:
    reviewer = FakeReviewer()

    review(DIFF_WITH_CONTEXT, reviewer)

    (call,) = reviewer.calls
    assert call["lines"] == [
        NumberedLine(40, "before", context=True),
        NumberedLine(41, "new_a"),
        NumberedLine(42, "new_b"),
        NumberedLine(43, "after", context=True),
    ]


def test_lines_reviewed_counts_only_added_lines_not_context() -> None:
    result = review(DIFF_WITH_CONTEXT)

    assert result.files[0].lines_reviewed == 2


def test_a_file_whose_only_lines_are_context_has_nothing_to_review() -> None:
    """A diff can show context with no additions (pure deletions); that's not reviewable."""
    diff = "\n".join(
        [
            "diff --git a/a.py b/a.py",
            "--- a/a.py",
            "+++ b/a.py",
            "@@ -1,3 +1,2 @@",
            " keep",
            "-gone",
            " keep2",
            "",
        ]
    )

    with pytest.raises(NoReviewableChangesError, match="no added"):
        review(diff)
