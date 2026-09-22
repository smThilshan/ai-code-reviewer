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


# Marker prefixed to context lines in the prompt. Kept as one constant so the
# rendering and the instructions to the model (see prompts.EXCERPT_NOTE) can't
# drift apart.
CONTEXT_MARKER = "[context]"


@dataclass(frozen=True, slots=True)
class NumberedLine:
    """One line of source and its 1-based line number in the original file."""

    number: int
    text: str

    context: bool = False
    """True for unchanged lines shown only to help understand nearby code.

    The model may read them but must not report issues on them. Whole-file
    review never uses this; it exists for pull-request excerpts.
    """


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
    """Format lines as "N: text", one per row, using each line's own number.

    Context lines get a "[context]" prefix. Where numbers skip (code that was
    left out between two shown regions) a "..." row marks the gap, so the model
    doesn't mistake two distant regions for adjacent code.
    """
    rows: list[str] = []
    previous: int | None = None
    for line in lines:
        if previous is not None and line.number != previous + 1:
            rows.append("...")
        prefix = f"{CONTEXT_MARKER} " if line.context else ""
        rows.append(f"{prefix}{line.number}: {line.text}")
        previous = line.number
    return "\n".join(rows)


def add_line_numbers(code: str) -> str:
    """Return `code` with "N: " prepended to every line, starting at 1.

    >>> add_line_numbers("def foo():\\n    pass")
    '1: def foo():\\n2:     pass'
    """
    return render_numbered_lines(number_lines(code))
