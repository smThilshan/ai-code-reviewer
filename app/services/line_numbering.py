"""Attach line numbers to source code before it goes to the LLM.

LLMs are unreliable at counting lines in a wall of text, so instead of asking
the model to count, we print the numbers next to the code and ask it to read
them. The model then copies "12" from the text rather than computing it.

A line is a (number, text) pair rather than just text, because Phase 5 reviews
*excerpts* (only the lines a pull request added), where numbers start
anywhere and skip. Carrying the real number with each line means the model is
shown, and answers with, the file's true line numbers; nothing has to be
translated back afterwards.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

# Only the line endings editors actually show as line breaks. We deliberately
# don't use str.splitlines(): it also splits on form feed, vertical tab and
# Unicode separators (U+2028, \x85, ...), which would make our numbering
# disagree with the line numbers the user sees in their editor.
_LINE_BREAK = re.compile(r"\r\n|\r|\n")


@dataclass(frozen=True, slots=True)
class NumberedLine:
    """One line of source and its 1-based line number in the original file."""

    number: int
    text: str


def number_lines(code: str) -> list[NumberedLine]:
    """Split `code` into lines numbered from 1.

    This is the single definition of "what counts as a line" for the whole
    app. Both the prompt and the range check below use it, so they can never
    disagree about how many lines the code has.
    """
    lines = _LINE_BREAK.split(code)

    # A trailing newline is a line terminator, not the start of another line;
    # without this, "a\nb\n" would gain a phantom empty line 3.
    if len(lines) > 1 and lines[-1] == "":
        lines.pop()

    return [NumberedLine(number, text) for number, text in enumerate(lines, start=1)]


def render_numbered_lines(lines: Iterable[NumberedLine]) -> str:
    """Format lines as "N: text", one per row, using each line's own number."""
    return "\n".join(f"{line.number}: {line.text}" for line in lines)


def add_line_numbers(code: str) -> str:
    """Return `code` with "N: " prepended to every line, starting at 1.

    >>> add_line_numbers("def foo():\\n    pass")
    '1: def foo():\\n2:     pass'
    """
    return render_numbered_lines(number_lines(code))
