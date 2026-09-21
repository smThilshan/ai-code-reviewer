"""Map file extensions to the language names we give the reviewer.

This doubles as the allowlist of what counts as "code" in a pull request: a
file whose extension isn't here (README.md, package-lock.json, logo.png) is
skipped rather than sent to the model. An allowlist beats trying to exclude
non-code, because the set of things that aren't code is unbounded, and every
file we wrongly send is a paid API call.
"""

from pathlib import PurePosixPath

_LANGUAGE_BY_EXTENSION: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".kt": "kotlin",
    ".scala": "scala",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".h": "c",
    ".cc": "c++",
    ".cpp": "c++",
    ".cxx": "c++",
    ".hpp": "c++",
    ".cs": "c#",
    ".swift": "swift",
    ".sh": "shell",
    ".bash": "shell",
    ".sql": "sql",
}


def language_for_path(path: str) -> str | None:
    """Return the language for a file path, or None if it isn't reviewable code."""
    return _LANGUAGE_BY_EXTENSION.get(PurePosixPath(path).suffix.lower())
