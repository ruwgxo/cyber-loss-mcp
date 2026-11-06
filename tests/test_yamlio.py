from __future__ import annotations

import pytest

from cyber_loss_mcp.validation import yamlio

from .conftest import error_text


def problems(text: str) -> str:
    _, issues = yamlio.load(text, "f.yaml")
    return error_text(issues)


def test_plain_document_loads() -> None:
    data, issues = yamlio.load("a: 1\nb: [x, y]\n", "f.yaml")
    assert data == {"a": 1, "b": ["x", "y"]}
    assert issues == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a: 1\na: 2\n", "duplicate key 'a'"),
        ("a: &x 1\nb: *x\n", "aliases are not allowed"),
        ("a: &x 1\n", "anchors are not allowed"),
        ("base: &b {x: 1}\nc:\n  <<: *b\n", "merge keys"),
        ("a: !!str 1\n", "explicit tag"),
        ("a: !custom 1\n", "YAML error"),
        ("a: |\n  one\n  two\n", "literal block scalar"),
        ("a: one\n  two\n", "folded block scalar"),
        ("a: 'one\n  two'\n", "folded block scalar"),
        ("a: >\n  the model''s output\n", "doubled apostrophe"),
        ("a: 2024-01-31\n", "dates must be quoted"),
        ("1: x\n", "mapping keys must be strings"),
        ("a: [1\n", "YAML error"),
        ("a: !!python/object:os.system x\n", "YAML error"),
    ],
)
def test_rejects(text: str, expected: str) -> None:
    assert expected in problems(text)


def test_folded_prose_is_accepted() -> None:
    _, issues = yamlio.load("a: >\n  one\n  two\n", "f.yaml")
    assert issues == []


def test_oversized_file_is_refused() -> None:
    data, issues = yamlio.load("a: " + "x" * yamlio.MAX_FILE_BYTES, "f.yaml")
    assert data is None
    assert "larger than" in error_text(issues)


def test_norway_problem_surfaces_as_a_boolean() -> None:
    # YAML 1.1 reads NO as false; the domain schema then rejects it (see test_incident).
    data, _ = yamlio.load("country: NO\n", "f.yaml")
    assert data == {"country": False}
