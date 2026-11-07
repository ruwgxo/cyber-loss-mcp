from __future__ import annotations

from typing import Any

import pytest

from cyber_loss_mcp.validation import document, paths, standard

from .conftest import error_text


def test_vendored_standard_matches_pin() -> None:
    assert standard.standard()["version"] == "2.0.0"


def test_tampered_standard_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    standard.standard.cache_clear()
    monkeypatch.setattr(paths, "STANDARD_SHA256", "0" * 64)
    try:
        with pytest.raises(standard.StandardPinError, match="expected 0000"):
            standard.standard()
    finally:
        monkeypatch.undo()
        standard.standard.cache_clear()


def _schema_examples() -> list[dict[str, Any]]:
    return [e for e in standard.standard()["conformance_examples"] if "schema_valid" in e]


@pytest.mark.parametrize("example", _schema_examples(), ids=lambda e: e["name"])
def test_standard_conformance_examples(example: dict[str, Any]) -> None:
    valid = not list(standard.root_validator().iter_errors(example["input"]))
    assert valid is example["schema_valid"]


@pytest.mark.parametrize("name", document.PROFILES)
def test_profiles_are_valid(name: str) -> None:
    prof, issues = document.load_profile(name)
    assert issues == []
    assert prof is not None
    assert prof["unmapped"] == "error"


def test_unknown_profile_is_refused() -> None:
    prof, issues = document.load_profile("not-a-profile.yaml")
    assert prof is None
    assert "not one of the dataset's profiles" in error_text(issues)


def test_profile_with_bad_path_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    original = paths.standards_file

    class Fake:
        def __init__(self, text: str) -> None:
            self.text = text

        def read_text(self, encoding: str) -> str:
            return self.text

    bad = (
        "record: PROFILE\ntitle: Bad\nupdated: '2026-11-06'\nstandard: '2.0.0'\n"
        "maps:\n  a.b-c:\n  - {visibility: internal}\n  ok: not-a-list\n"
    )
    monkeypatch.setattr(
        paths,
        "standards_file",
        lambda name: Fake(bad) if name == paths.INCIDENT_PROFILE else original(name),
    )
    prof, issues = document.load_profile(paths.INCIDENT_PROFILE)
    assert prof is None
    text = error_text(issues)
    assert "invalid path segment" in text
    assert "templates must be a list" in text
