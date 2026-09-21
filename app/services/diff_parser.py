"""Parse a unified diff and extract the lines each file *added*.

Anatomy of a unified diff (what GitHub returns for a pull request):

    diff --git a/app/foo.py b/app/foo.py      <- starts a file section
    index 83db48f..bf2a3c1 100644             <- metadata (ignored)
    --- a/app/foo.py                          <- old path
    +++ b/app/foo.py                          <- new path
    @@ -10,7 +10,8 @@ def bar():               <- a "hunk" header
     def bar():                               <- ' ' context: in BOTH versions
    -    return 1                             <- '-' removed: OLD version only
    +    total = compute()                    <- '+' added:   NEW version only
    +    return total                         <- '+' added
     print("done")                            <- ' ' context

How we tell the three kinds of line apart: by the FIRST CHARACTER of each line
inside a hunk. ' ' is context, '-' was removed, '+' was added. (A line that was
"changed" appears as a '-' followed by a '+'; we keep the '+' side, which is
the new content.)

How we find each added line's REAL line number in the new file: the hunk header
`@@ -10,7 +10,8 @@` says "this hunk covers 7 lines of the old file starting at
line 10, and 8 lines of the new file starting at line 10". So we start a
counter at the new-file start (10) and walk the hunk:

  - context line  -> it exists in the new file: counter += 1
  - added line    -> it exists in the new file: record (counter, text); counter += 1
  - removed line  -> it does NOT exist in the new file: counter is unchanged

That counter is the line number an editor would show for the file at the PR's
head commit. It is NOT the diff's own numbering (position within the diff
text, which GitHub uses for inline review comments), and it is not the old
file's numbering either. Removed lines never advance it, which is exactly why
the two numberings drift apart.

The hardest parsing trap: inside a hunk, a removed line whose content starts
with "-- " (an SQL comment) is written "--- ...", and an added line starting
with "++" is written "+++ ...". Those look exactly like the `---`/`+++` file
headers. So we never decide by looking at the text; we use the hunk header's
counts to know precisely how many lines belong to the hunk, and treat lines as
headers only when we are outside one.
"""

import re
from dataclasses import dataclass, field

from app.services.line_numbering import NumberedLine

# "@@ -old_start[,old_count] +new_start[,new_count] @@". A missing count means 1.
_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_DIFF_GIT_HEADER = re.compile(r"^diff --git a/(.+?) b/(.+)$")


@dataclass(frozen=True, slots=True)
class FileDiff:
    """What one file's section of a diff tells us."""

    path: str
    """Path of the file in the new version (or the old one, if deleted)."""

    added_lines: tuple[NumberedLine, ...]
    """Lines added or changed, each with its real line number in the new file."""

    is_binary: bool = False
    is_deleted: bool = False


@dataclass
class _FileBuilder:
    """Mutable scratch state while a file's section is being read."""

    header_path: str = ""
    old_path: str | None = None
    new_path: str | None = None
    renamed_to: str | None = None
    is_binary: bool = False
    is_deleted: bool = False
    added: list[NumberedLine] = field(default_factory=list)

    def build(self) -> FileDiff:
        # Best source of the path first: "+++ b/x", then "rename to", then the
        # "diff --git" line (ambiguous if a name contains " b/"), and for a
        # deleted file "+++" is /dev/null so fall back to the old path.
        path = self.new_path or self.renamed_to or self.old_path or self.header_path
        return FileDiff(
            path=path,
            added_lines=tuple(self.added),
            is_binary=self.is_binary,
            is_deleted=self.is_deleted,
        )


def parse_diff(diff_text: str) -> list[FileDiff]:
    """Parse a unified diff into one FileDiff per changed file, in diff order."""
    files: list[FileDiff] = []
    current: _FileBuilder | None = None

    # Lines left in the current hunk, per the hunk header's counts; the hunk
    # (and thus "content mode") ends when both reach zero. See module docstring.
    old_left = new_left = 0
    new_line = 0

    # split("\n"), not splitlines(): file content may itself contain \r, \x0c
    # or U+2028, which splitlines() would treat as line breaks and corrupt the
    # line accounting.
    for raw in diff_text.split("\n"):
        if old_left > 0 or new_left > 0:
            # Inside a hunk: the first character says what kind of line this is.
            marker, text = raw[:1], raw[1:]
            if marker == "+":
                assert current is not None
                current.added.append(NumberedLine(new_line, text.removesuffix("\r")))
                new_line += 1
                new_left -= 1
            elif marker == "-":
                old_left -= 1  # gone from the new file: does not advance new_line
            elif marker == "\\":
                pass  # "\ No newline at end of file": a note, not a line
            else:
                # ' ' context. An entirely empty line also counts, because some
                # tools strip the single trailing space off blank context lines.
                old_left -= 1
                new_left -= 1
                new_line += 1
            continue

        # Outside a hunk: file headers and metadata.
        if raw.startswith("diff --git "):
            if current is not None:
                files.append(current.build())
            current = _FileBuilder()
            match = _DIFF_GIT_HEADER.match(raw)
            if match:
                current.header_path = match.group(2)
        elif current is None:
            continue  # preamble before the first file
        elif (match := _HUNK_HEADER.match(raw)) is not None:
            old_left = int(match.group(2)) if match.group(2) is not None else 1
            new_left = int(match.group(4)) if match.group(4) is not None else 1
            new_line = int(match.group(3))
        elif raw.startswith("--- "):
            current.old_path = _clean_path(raw[4:], "a/")
        elif raw.startswith("+++ "):
            current.new_path = _clean_path(raw[4:], "b/")
        elif raw.startswith("rename to "):
            current.renamed_to = raw[len("rename to ") :]
        elif raw.startswith("deleted file mode"):
            current.is_deleted = True
        elif raw.startswith(("Binary files ", "GIT binary patch")):
            current.is_binary = True

    if current is not None:
        files.append(current.build())
    return files


def _clean_path(token: str, prefix: str) -> str | None:
    """Turn a '---'/'+++' path token into a plain path, or None for /dev/null.

    `prefix` is the single marker git puts on that side ("a/" for the old
    file, "b/" for the new one). Strip only that one: a real directory named
    "b" would otherwise lose a second, genuine path component.
    """
    # git appends a tab after paths containing spaces.
    path = token.split("\t", 1)[0].strip().strip('"')
    if path == "/dev/null":
        return None
    return path.removeprefix(prefix)
