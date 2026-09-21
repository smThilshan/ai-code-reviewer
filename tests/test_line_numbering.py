"""Tests for add_line_numbers and the user message that embeds it."""

from app.services.line_numbering import (
    NumberedLine,
    add_line_numbers,
    number_lines,
    render_numbered_lines,
)
from app.services.prompts import EXCERPT_NOTE, build_user_message


def test_numbers_each_line_starting_at_one() -> None:
    assert add_line_numbers("def foo():\n    pass") == "1: def foo():\n2:     pass"


def test_single_line() -> None:
    assert add_line_numbers("x = 1") == "1: x = 1"


def test_trailing_newline_does_not_create_phantom_line() -> None:
    assert add_line_numbers("a\nb\n") == "1: a\n2: b"


def test_blank_lines_in_the_middle_are_numbered() -> None:
    assert add_line_numbers("a\n\nb") == "1: a\n2: \n3: b"


def test_windows_and_old_mac_line_endings_count_as_one_break_each() -> None:
    assert add_line_numbers("a\r\nb\r\nc") == "1: a\n2: b\n3: c"
    assert add_line_numbers("a\rb") == "1: a\n2: b"


def test_indentation_and_tabs_are_preserved() -> None:
    assert add_line_numbers("if x:\n\treturn 1") == "1: if x:\n2: \treturn 1"


def test_unicode_separators_do_not_split_lines() -> None:
    """Editors don't show \\u2028 or form feed as line breaks; neither should we."""
    code = "s = 'a\u2028b'\nt = 2\x0cu = 3"

    numbered = add_line_numbers(code)

    assert numbered.count("\n") == 1  # exactly two lines
    assert numbered.startswith("1: s = 'a\u2028b'")


def test_number_lines_returns_line_objects_counting_from_one() -> None:
    assert number_lines("a\nb\n") == [NumberedLine(1, "a"), NumberedLine(2, "b")]


def test_render_uses_each_lines_own_number_so_gaps_are_preserved() -> None:
    """PR excerpts skip numbers; rendering must show the real ones, not 1..N."""
    lines = [NumberedLine(12, "x = 1"), NumberedLine(13, "y = 2"), NumberedLine(40, "z = 3")]

    assert render_numbered_lines(lines) == "12: x = 1\n13: y = 2\n40: z = 3"


def test_user_message_contains_language_and_numbered_code_in_tags() -> None:
    message = build_user_message(number_lines("x = 1\ny = 2"), "python")

    assert message == "Language: python\n\n<code>\n1: x = 1\n2: y = 2\n</code>"


def test_excerpt_note_appears_only_when_requested() -> None:
    lines = [NumberedLine(7, "x = 1")]

    assert EXCERPT_NOTE not in build_user_message(lines, "python")
    assert EXCERPT_NOTE in build_user_message(lines, "python", excerpt=True)
