"""Tests for build_system_prompt and the LANGUAGE_NOTES table."""

from app.services.languages import normalize_language
from app.services.prompts import LANGUAGE_NOTES, SYSTEM_PROMPT, build_system_prompt


def test_unknown_or_none_language_returns_the_bare_rubric_unchanged() -> None:
    assert build_system_prompt(None) == SYSTEM_PROMPT
    assert build_system_prompt("cobol") == SYSTEM_PROMPT


def test_known_language_appends_exactly_one_note_after_the_rubric() -> None:
    prompt = build_system_prompt("python")

    assert prompt.startswith(SYSTEM_PROMPT)
    addition = prompt.removeprefix(SYSTEM_PROMPT)
    assert addition.count("LANGUAGE-SPECIFIC THINGS TO CHECK") == 1
    assert LANGUAGE_NOTES["python"] in addition


def test_every_note_is_keyed_by_a_canonical_language_name() -> None:
    """A note keyed by a raw alias (e.g. 'py') would silently never be found."""
    for language in LANGUAGE_NOTES:
        assert normalize_language(language) == language


def test_notes_exist_for_every_language_the_phase_6_evaluation_covered() -> None:
    for language in ("python", "javascript", "java", "go", "c"):
        assert language in LANGUAGE_NOTES


def test_each_note_is_a_single_short_line() -> None:
    """A long note is an ongoing token cost on every request in that language."""
    for language, note in LANGUAGE_NOTES.items():
        assert "\n" not in note, language
        assert len(note) < 400, language
