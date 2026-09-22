"""Tests for language detection: extensions, aliases, and resolution order."""

import pytest

from app.services.languages import language_for_path, normalize_language, resolve_language


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("app/main.py", "python"),
        ("src/index.js", "javascript"),
        ("src/App.jsx", "javascript"),
        ("lib/util.mjs", "javascript"),
        ("src/app.ts", "typescript"),
        ("src/App.tsx", "typescript"),
        ("src/Main.java", "java"),
        ("cmd/server/main.go", "go"),
        ("src/lib.rs", "rust"),
        ("app/models/user.rb", "ruby"),
        ("index.php", "php"),
        ("src/main.c", "c"),
        ("src/main.cpp", "c++"),
        ("src/Program.cs", "c#"),
        ("scripts/deploy.sh", "shell"),
        ("db/schema.sql", "sql"),
        ("SRC/MAIN.PY", "python"),  # extension matching ignores case
        ("a.b.c/d.e.py", "python"),  # only the last suffix counts
        ("src\\main.py", "python"),  # Windows-style separator
    ],
)
def test_known_extensions_map_to_languages(path: str, expected: str) -> None:
    assert language_for_path(path) == expected


@pytest.mark.parametrize(
    "path", ["README.md", "notes.txt", "data.json", "logo.png", "Makefile", "Dockerfile", ".gitignore", "py", ""]
)
def test_non_code_or_extensionless_files_have_no_language(path: str) -> None:
    assert language_for_path(path) is None


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("Python", "python"),
        ("py", "python"),
        ("PYTHON3", "python"),
        ("JS", "javascript"),
        ("node", "javascript"),
        ("Node.js", "javascript"),
        ("ts", "typescript"),
        ("Golang", "go"),
        ("C++", "c++"),
        ("cpp", "c++"),
        ("C#", "c#"),
        ("csharp", "c#"),
        ("bash", "shell"),
        ("  rust  ", "rust"),
        ("Haskell", "haskell"),  # unknown languages pass through, lower-cased
    ],
)
def test_language_names_are_normalized(given: str, expected: str) -> None:
    assert normalize_language(given) == expected


def test_explicit_language_wins_over_filename() -> None:
    assert resolve_language("go", "script.py") == "go"


def test_explicit_language_is_normalized() -> None:
    assert resolve_language("JS", None) == "javascript"


def test_filename_is_used_when_language_is_missing_or_blank() -> None:
    assert resolve_language(None, "app/main.py") == "python"
    assert resolve_language("", "app/main.py") == "python"
    assert resolve_language("   ", "app/main.py") == "python"


def test_unknown_when_neither_is_usable() -> None:
    assert resolve_language(None, None) is None
    assert resolve_language(None, "README.md") is None
    assert resolve_language(None, "Makefile") is None

def test_ambiguous_c_header_gets_its_own_language_label() -> None:
    """.h is genuinely ambiguous; it must not silently claim to be plain C."""
    from app.services.languages import AMBIGUOUS_C_HEADER

    assert language_for_path("include/widget.h") == AMBIGUOUS_C_HEADER
    assert AMBIGUOUS_C_HEADER not in ("c", "c++")


@pytest.mark.parametrize(
    ("path", "expected"), [("a.cc", "c++"), ("a.cpp", "c++"), ("a.hpp", "c++"), ("a.hh", "c++"), ("a.c", "c")]
)
def test_unambiguous_c_and_cpp_extensions_are_not_affected(path: str, expected: str) -> None:
    assert language_for_path(path) == expected
