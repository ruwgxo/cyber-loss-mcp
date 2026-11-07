from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from cyber_loss_mcp.validation import document

from .conftest import TODAY, dump, error_text

ROOT = Path(__file__).parent.parent


def load(name: str) -> dict[str, Any]:
    data = yaml.safe_load((ROOT / "logs" / f"{name}.yaml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def unverified_entry(n: int, **overrides: str) -> dict[str, str]:
    entry = {
        "id": f"unv-{n}",
        "date": "2026-11-01",
        "organisation": "Example Manufacturing Inc.",
        "claim": "$50 million total cost",
        "seen_in": "news report; no primary source found",
        "reason": "The figure does not appear in any filing.",
        "status": "open",
        "supersedes": "none",
    }
    entry.update(overrides)
    return entry


def check(doc: dict[str, Any], base: dict[str, Any] | None = None) -> str:
    file = f"logs/{doc['id'].split('-')[0]}.yaml"
    base_text = dump(base) if base is not None else None
    return error_text(document.validate(dump(doc), file, TODAY, base_text))


@pytest.mark.parametrize("name", ["unverified", "corrections"])
def test_committed_logs_are_valid(name: str) -> None:
    text = (ROOT / "logs" / f"{name}.yaml").read_text(encoding="utf-8")
    assert document.validate(text, f"logs/{name}.yaml", TODAY) == []


def test_entries_and_supersession() -> None:
    doc = load("unverified")
    doc["entries"] = [
        unverified_entry(1),
        unverified_entry(2, date="2026-11-02", status="rejected", supersedes="unv-1"),
    ]
    assert check(doc) == ""


def test_corrections_entry() -> None:
    doc = load("corrections")
    doc["entries"] = [
        {
            "id": "cor-1",
            "date": "2026-11-01",
            "dataset_version": "0.2.0",
            "incident": "inc-2024-example-manufacturing",
            "figure": "fig-1",
            "field": "values.amount",
            "old_value": "12345678",
            "new_value": "12300000",
            "reported_in": "GitHub issue 1",
            "evidence": "Form 10-Q page 31 states approximately $12.3 million.",
            "supersedes": "none",
        }
    ]
    assert check(doc) == ""


@pytest.mark.parametrize(
    ("entries", "expected"),
    [
        ([unverified_entry(2)], "expected unv-1"),
        ([unverified_entry(1, date="2026-11-03"), unverified_entry(2)], "date order"),
        ([unverified_entry(1, supersedes="unv-2"), unverified_entry(2)], "not an earlier entry"),
        ([unverified_entry(1, date="2026-11-07")], "earlier than the last entry"),
        ([unverified_entry(1, status="maybe")], "is not one of"),
        ([{**unverified_entry(1), "url": "https://x"}], "Additional properties"),
    ],
)
def test_entry_rules(entries: list[dict[str, str]], expected: str) -> None:
    doc = load("unverified")
    doc["entries"] = entries
    if expected == "earlier than the last entry":
        doc["updated"] = "2026-11-06"
    assert expected in check(doc)


def test_append_only_against_base() -> None:
    base = load("unverified")
    base["entries"] = [unverified_entry(1)]
    appended = copy.deepcopy(base)
    appended["entries"].append(unverified_entry(2, status="included", supersedes="unv-1"))
    assert check(appended, base) == ""

    edited = copy.deepcopy(base)
    edited["entries"][0]["reason"] = "Changed my mind."
    assert "append-only" in check(edited, base)

    removed = copy.deepcopy(base)
    removed["entries"] = []
    assert "append-only" in check(removed, base)


def test_log_profile_must_match() -> None:
    doc = load("unverified")
    doc["profile"] = "../src/cyber_loss_mcp/standards/other.yaml"
    assert "was expected" in check(doc)
