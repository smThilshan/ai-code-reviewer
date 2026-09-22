"""Map file extensions to the language names we give the reviewer.

This doubles as the allowlist of what counts as "code" in a pull request: a
file whose extension isn't here (README.md, package-lock.json, logo.png) is
skipped rather than sent to the model. An allowlist beats trying to exclude
non-code, because the set of things that aren't code is unbounded, and every
file we wrongly send is a paid API call.
"""

from pathlib import PurePosixPath

# A bare ".h" is genuinely ambiguous: it's the standard header extension for
# both C and C++ (unlike ".hpp"/".hh", which are conventionally C++-only), and
# the extension alone can't tell them apart. "c/c++" says that honestly
# instead of silently guessing "c" and being wrong for a C++ header — or,
# worse, excluding .h files from review entirely, which is what mapping this
# to None would do (see language_for_path). It's a distinct language label
# from both "c" and "c++"; app.services.prompts.LANGUAGE_NOTES has a matching
# entry that tells the model how to tell the two apart from the code.
AMBIGUOUS_C_HEADER = "c/c++"

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
    ".h": AMBIGUOUS_C_HEADER,
    ".cc": "c++",
    ".cpp": "c++",
    ".cxx": "c++",
    ".hpp": "c++",
    ".hh": "c++",
    ".cs": "c#",
    ".swift": "swift",
    ".sh": "shell",
    ".bash": "shell",
    ".sql": "sql",
}


def language_for_path(path: str) -> str | None:
    """Return the language for a file path, or None if it isn't reviewable code."""
    return _LANGUAGE_BY_EXTENSION.get(PurePosixPath(path).suffix.lower())


# Names people actually type, mapped to the canonical names used above. Keeping
# one canonical spelling matters: "js", "JS" and "node" should all reach the
# model as "javascript", so the prompt (and any per-language tuning later)
# sees one consistent value.
_LANGUAGE_ALIASES: dict[str, str] = {
    "py": "python",
    "py3": "python",
    "python3": "python",
    "js": "javascript",
    "jsx": "javascript",
    "node": "javascript",
    "nodejs": "javascript",
    "node.js": "javascript",
    "ecmascript": "javascript",
    "ts": "typescript",
    "tsx": "typescript",
    "golang": "go",
    "rs": "rust",
    "rb": "ruby",
    "kt": "kotlin",
    "cpp": "c++",
    "cxx": "c++",
    "cc": "c++",
    "csharp": "c#",
    "cs": "c#",
    "sh": "shell",
    "bash": "shell",
    "zsh": "shell",
}


def normalize_language(name: str) -> str:
    """Lower-case a user-supplied language name and map common aliases to canonical ones.

    Unknown languages pass through (lower-cased), not rejected: the language is
    only a hint to the model, and it may well know "haskell" or "elixir".
    """
    key = name.strip().lower()
    return _LANGUAGE_ALIASES.get(key, key)


def resolve_language(language: str | None, filename: str | None) -> str | None:
    """Decide which language to tell the model the code is in.

    Priority: (1) what the user said explicitly, (2) the filename's extension,
    (3) None, meaning "unknown". With None, the prompt asks the model to
    identify the language itself, which it can do reliably for real code, at no
    extra cost. We deliberately don't build our own content sniffer: heuristics
    for telling languages apart are brittle, and the model does it better.
    """
    if language and language.strip():
        return normalize_language(language)
    if filename:
        return language_for_path(filename)
    return None
