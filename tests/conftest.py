from __future__ import annotations

import copy
import datetime as dt
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from cyber_loss_mcp.validation import document
from cyber_loss_mcp.validation.report import Issue, errors

FIXTURES = Path(__file__).parent / "fixtures"
INCIDENT_FIXTURE = FIXTURES / "inc-2024-example-manufacturing.yaml"
TODAY = dt.date(2026, 11, 6)

Validate = Callable[[dict[str, Any]], list[Issue]]


def _strip(value: Any) -> Any:
    if isinstance(value, str):
        return value.rstrip("\n")
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def dump(doc: dict[str, Any]) -> str:
    """Serialise a test document. Folded scalars' final newlines are dropped and lines
    are wide, so every string stays on one line and passes the scalar-style check."""
    return yaml.safe_dump(_strip(doc), sort_keys=False, allow_unicode=True, width=10**6)


def error_text(issues: list[Issue]) -> str:
    return "\n".join(str(i) for i in errors(issues))


@pytest.fixture
def incident() -> dict[str, Any]:
    """A fresh copy of the fictional, valid incident fixture."""
    data = yaml.safe_load(INCIDENT_FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return copy.deepcopy(data)


@pytest.fixture
def validate_incident() -> Validate:
    def run(doc: dict[str, Any]) -> list[Issue]:
        return document.validate(dump(doc), f"incidents/{doc['id']}.yaml", TODAY)

    return run
