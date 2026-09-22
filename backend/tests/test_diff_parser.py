"""Tests for parse_diff, using small hand-written unified diffs.

The parser's whole job is getting each added line's REAL line number in the
new file right. The rules being tested are spelled out in the parser's module
docstring; the comments in each test say which trap it guards.
"""

from app.services.diff_parser import parse_diff
from app.services.line_numbering import NumberedLine


def make_diff(*lines: str) -> str:
    return "\n".join(lines) + "\n"


def added(diff_text: str, index: int = 0) -> list[tuple[int, str]]:
    """(line_number, text) pairs added by the `index`-th file in the diff."""
    return [(line.number, line.text) for line in parse_diff(diff_text)[index].added_lines]


# --- The core rule: added lines get their real new-file line numbers ---------


def test_added_lines_get_new_file_line_numbers_and_context_advances_the_counter() -> None:
    diff = make_diff(
        "diff --git a/app/foo.py b/app/foo.py",
        "index 83db48f..bf2a3c1 100644",
        "--- a/app/foo.py",
        "+++ b/app/foo.py",
        "@@ -10,4 +10,5 @@ def bar():",
        " def bar():",  # new line 10 (context)
        "-    return 1",  # removed: not in new file
        "+    total = compute()",  # new line 11
        "+    return total",  # new line 12
        ' print("done")',  # new line 13
        " x = 1",  # new line 14
    )

    (file,) = parse_diff(diff)

    assert file.path == "app/foo.py"
    assert [(line.number, line.text) for line in file.added_lines] == [
        (11, "    total = compute()"),
        (12, "    return total"),
    ]


def test_removed_lines_do_not_advance_the_new_file_counter() -> None:
    """Old and new numbering drift apart here: 'e' is line 5 in the old file, 3 in the new."""
    diff = make_diff(
        "diff --git a/f.py b/f.py",
        "--- a/f.py",
        "+++ b/f.py",
        "@@ -1,6 +1,4 @@",
        " a",  # 1
        "-b",
        "-c",
        "-d",
        "+D",  # 2
        " e",  # 3
        " f",  # 4
    )

    assert added(diff) == [(2, "D")]


def test_context_lines_are_never_reported_as_added() -> None:
    diff = make_diff(
        "diff --git a/f.py b/f.py",
        "--- a/f.py",
        "+++ b/f.py",
        "@@ -1,3 +1,3 @@",
        " keep1",
        "-old",
        "+new",
        " keep2",
    )

    assert added(diff) == [(2, "new")]


def test_each_hunk_restarts_the_counter_from_its_own_header() -> None:
    diff = make_diff(
        "diff --git a/f.py b/f.py",
        "--- a/f.py",
        "+++ b/f.py",
        "@@ -1,2 +1,3 @@",
        " a",
        "+ADDED_AT_2",
        " b",
        "@@ -50,2 +51,3 @@",  # new numbering is now offset by +1 from the old
        " y",
        "+ADDED_AT_52",
        " z",
    )

    assert added(diff) == [(2, "ADDED_AT_2"), (52, "ADDED_AT_52")]


def test_new_file_is_numbered_from_one() -> None:
    diff = make_diff(
        "diff --git a/new.py b/new.py",
        "new file mode 100644",
        "index 0000000..abc1234",
        "--- /dev/null",
        "+++ b/new.py",
        "@@ -0,0 +1,3 @@",
        "+first",
        "+second",
        "+third",
    )

    (file,) = parse_diff(diff)

    assert file.path == "new.py"
    assert [(line.number, line.text) for line in file.added_lines] == [(1, "first"), (2, "second"), (3, "third")]


# --- Traps -------------------------------------------------------------------


def test_header_lookalike_lines_inside_a_hunk_are_content_not_headers() -> None:
    """A removed "-- comment" shows as '--- comment'; an added "++ x" as '+++ x'."""
    diff = make_diff(
        "diff --git a/q.sql b/q.sql",
        "--- a/q.sql",
        "+++ b/q.sql",
        "@@ -1,3 +1,3 @@",
        " SELECT 1;",
        "--- a comment that was removed",
        "+++ a line that was added",
        " SELECT 2;",
    )

    (file,) = parse_diff(diff)

    assert file.path == "q.sql"  # not overwritten by the "+++ a line..." content
    assert [(line.number, line.text) for line in file.added_lines] == [(2, "++ a line that was added")]


def test_diff_git_lookalike_inside_a_hunk_does_not_start_a_new_file() -> None:
    diff = make_diff(
        "diff --git a/notes.py b/notes.py",
        "--- a/notes.py",
        "+++ b/notes.py",
        "@@ -1 +1,2 @@",
        " keep",
        "+diff --git a/fake b/fake",
    )

    files = parse_diff(diff)

    assert len(files) == 1
    assert added(diff) == [(2, "diff --git a/fake b/fake")]


def test_no_newline_marker_is_not_counted_as_a_line() -> None:
    diff = make_diff(
        "diff --git a/f.py b/f.py",
        "--- a/f.py",
        "+++ b/f.py",
        "@@ -1,2 +1,2 @@",
        " a",
        "-b",
        "\\ No newline at end of file",
        "+b",
        "\\ No newline at end of file",
    )

    assert added(diff) == [(2, "b")]


def test_hunk_header_without_counts_means_one_line() -> None:
    diff = make_diff(
        "diff --git a/f.py b/f.py",
        "--- a/f.py",
        "+++ b/f.py",
        "@@ -7 +7 @@",
        "-x",
        "+y",
    )

    assert added(diff) == [(7, "y")]


def test_blank_context_line_missing_its_leading_space_still_counts() -> None:
    diff = make_diff(
        "diff --git a/f.py b/f.py",
        "--- a/f.py",
        "+++ b/f.py",
        "@@ -1,3 +1,3 @@",
        " a",
        "",  # a blank context line whose single space was stripped
        "-b",
        "+c",
    )

    assert added(diff) == [(3, "c")]


def test_carriage_return_is_stripped_from_added_lines_of_crlf_files() -> None:
    diff = make_diff(
        "diff --git a/f.py b/f.py",
        "--- a/f.py",
        "+++ b/f.py",
        "@@ -1 +1,2 @@",
        " a\r",
        "+b\r",
    )

    assert added(diff) == [(2, "b")]


def test_form_feed_and_unicode_separator_inside_a_line_do_not_split_it() -> None:
    diff = make_diff(
        "diff --git a/f.py b/f.py",
        "--- a/f.py",
        "+++ b/f.py",
        "@@ -0,0 +1,2 @@",
        "+a\x0cb",
        "+c d",
    )

    assert added(diff) == [(1, "a\x0cb"), (2, "c d")]


# --- File-level cases --------------------------------------------------------


def test_files_are_returned_in_diff_order_without_bleeding_into_each_other() -> None:
    diff = make_diff(
        "diff --git a/one.py b/one.py",
        "--- a/one.py",
        "+++ b/one.py",
        "@@ -1 +1,2 @@",
        " a",
        "+ONE",
        "diff --git a/two.py b/two.py",
        "--- a/two.py",
        "+++ b/two.py",
        "@@ -5,1 +5,2 @@",
        " e",
        "+TWO",
    )

    files = parse_diff(diff)

    assert [f.path for f in files] == ["one.py", "two.py"]
    assert added(diff, 0) == [(2, "ONE")]
    assert added(diff, 1) == [(6, "TWO")]


def test_deleted_file_is_flagged_and_keeps_its_old_path() -> None:
    diff = make_diff(
        "diff --git a/old.py b/old.py",
        "deleted file mode 100644",
        "index abc1234..0000000",
        "--- a/old.py",
        "+++ /dev/null",
        "@@ -1,2 +0,0 @@",
        "-gone1",
        "-gone2",
    )

    (file,) = parse_diff(diff)

    assert file.is_deleted
    assert file.path == "old.py"
    assert file.added_lines == ()


def test_pure_rename_uses_the_new_path_and_has_no_added_lines() -> None:
    diff = make_diff(
        "diff --git a/old_name.py b/new_name.py",
        "similarity index 100%",
        "rename from old_name.py",
        "rename to new_name.py",
    )

    (file,) = parse_diff(diff)

    assert file.path == "new_name.py"
    assert file.added_lines == ()
    assert not file.is_deleted


def test_rename_with_edits_reports_lines_against_the_new_path() -> None:
    diff = make_diff(
        "diff --git a/old_name.py b/new_name.py",
        "similarity index 90%",
        "rename from old_name.py",
        "rename to new_name.py",
        "--- a/old_name.py",
        "+++ b/new_name.py",
        "@@ -1 +1,2 @@",
        " a",
        "+b",
    )

    (file,) = parse_diff(diff)

    assert file.path == "new_name.py"
    assert [(line.number, line.text) for line in file.added_lines] == [(2, "b")]


def test_binary_file_is_flagged_and_gets_its_path_from_the_diff_header() -> None:
    diff = make_diff(
        "diff --git a/logo.png b/logo.png",
        "index 1111111..2222222 100644",
        "Binary files a/logo.png and b/logo.png differ",
    )

    (file,) = parse_diff(diff)

    assert file.is_binary
    assert file.path == "logo.png"
    assert file.added_lines == ()


def test_mode_change_only_has_no_added_lines() -> None:
    diff = make_diff(
        "diff --git a/run.sh b/run.sh",
        "old mode 100644",
        "new mode 100755",
    )

    (file,) = parse_diff(diff)

    assert file.path == "run.sh"
    assert file.added_lines == ()


def test_directory_named_b_is_not_over_stripped() -> None:
    """Only the single 'a/' or 'b/' git prefix is removed, never a real 'b/' directory."""
    diff = make_diff(
        "diff --git a/b/x.py b/b/x.py",
        "--- a/b/x.py",
        "+++ b/b/x.py",
        "@@ -1 +1,2 @@",
        " a",
        "+b",
    )

    assert parse_diff(diff)[0].path == "b/x.py"


def test_path_with_spaces_and_trailing_tab_is_cleaned() -> None:
    diff = make_diff(
        "diff --git a/my file.py b/my file.py",
        "--- a/my file.py\t",
        "+++ b/my file.py\t",
        "@@ -1 +1,2 @@",
        " a",
        "+b",
    )

    assert parse_diff(diff)[0].path == "my file.py"


def test_empty_diff_and_preamble_yield_no_files() -> None:
    assert parse_diff("") == []
    assert parse_diff("just some text\nwith no diff in it\n") == []


def test_added_lines_carry_numberedline_objects() -> None:
    diff = make_diff(
        "diff --git a/f.py b/f.py",
        "--- a/f.py",
        "+++ b/f.py",
        "@@ -0,0 +1 @@",
        "+x",
    )

    assert parse_diff(diff)[0].added_lines == (NumberedLine(1, "x"),)


# --- Context lines ------------------------------------------------------------


def test_context_lines_are_kept_with_real_numbers_and_flagged_in_file_order() -> None:
    diff = make_diff(
        "diff --git a/f.py b/f.py",
        "--- a/f.py",
        "+++ b/f.py",
        "@@ -10,4 +10,5 @@",
        " ctx10",
        "-removed",
        "+added11",
        "+added12",
        " ctx13",
        " ctx14",
    )

    (file,) = parse_diff(diff)

    assert [(line.number, line.text, line.context) for line in file.lines] == [
        (10, "ctx10", True),
        (11, "added11", False),
        (12, "added12", False),
        (13, "ctx13", True),
        (14, "ctx14", True),
    ]
    # `added_lines` is the same data with context filtered out.
    assert [(line.number, line.text) for line in file.added_lines] == [(11, "added11"), (12, "added12")]


def test_removed_lines_appear_nowhere_in_the_lines() -> None:
    diff = make_diff(
        "diff --git a/f.py b/f.py",
        "--- a/f.py",
        "+++ b/f.py",
        "@@ -1,3 +1,2 @@",
        " keep",
        "-DELETED_LINE",
        " also keep",
    )

    (file,) = parse_diff(diff)

    assert all("DELETED_LINE" not in line.text for line in file.lines)
    assert [line.number for line in file.lines] == [1, 2]  # numbering closes over the removal


def test_separate_hunks_leave_a_gap_in_the_numbers() -> None:
    diff = make_diff(
        "diff --git a/f.py b/f.py",
        "--- a/f.py",
        "+++ b/f.py",
        "@@ -1,1 +1,2 @@",
        " a",
        "+A",
        "@@ -50,1 +51,2 @@",
        " y",
        "+Y",
    )

    (file,) = parse_diff(diff)

    assert [line.number for line in file.lines] == [1, 2, 51, 52]


def test_blank_context_line_is_kept_as_an_empty_context_line() -> None:
    diff = make_diff(
        "diff --git a/f.py b/f.py",
        "--- a/f.py",
        "+++ b/f.py",
        "@@ -1,3 +1,3 @@",
        " a",
        "",
        "-b",
        "+c",
    )

    (file,) = parse_diff(diff)

    assert [(line.number, line.text, line.context) for line in file.lines] == [
        (1, "a", True),
        (2, "", True),
        (3, "c", False),
    ]
