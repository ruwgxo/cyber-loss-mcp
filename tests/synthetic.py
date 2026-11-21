"""Fictional incident records for testing tool logic, built from the fictional fixture.

Every record here passes the full validator; the companies and figures are invented.
"""

from __future__ import annotations

import copy
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from .conftest import INCIDENT_FIXTURE, dump

BASE: dict[str, Any] = yaml.safe_load(INCIDENT_FIXTURE.read_text(encoding="utf-8"))


def money_text(amount: Decimal) -> str:
    return f"${amount:,}"


def incident(
    n: int,
    *,
    amounts: list[tuple[str, str]] | None = None,
    loss_type: str = "remediation",
    status: str = "reported",
    attack_types: list[str] | None = None,
    sector: str = "31-33",
    country: str = "US",
    insurance_basis: str = "gross",
    cumulative: bool = False,
) -> dict[str, Any]:
    """A fictional incident ``inc-2024-synthetic-<n>``. ``amounts`` is a list of
    (as_stated, amount_or_range) pairs; a range is written 'low..high'."""
    doc = copy.deepcopy(BASE)
    doc["id"] = f"inc-2024-synthetic-{n}"
    doc["title"] = f"Synthetic incident {n}"
    inc = doc["incident"]
    inc.update(organisation=f"Synthetic Company {n} Inc.", sector=sector, country=country)
    inc["attack_types"] = attack_types or ["ransomware"]
    template = doc["loss_figures"][0]
    figures, verification = [], []
    for k, (as_stated, value) in enumerate(amounts or [("$1,000,000", "1000000")], start=1):
        f = copy.deepcopy(template)
        f.update(
            id=f"fig-{k}",
            as_stated=as_stated,
            loss_type=loss_type,
            status=status,
            insurance_basis=insurance_basis,
        )
        f["quote"] = f"Fictional source sentence stating {as_stated} of losses."
        values: dict[str, Any] = {"period_end": "2024-03-31", "cumulative": cumulative}
        lowered = as_stated.lower()
        if ".." in value:
            low, high = value.split("..")
            values.update(qualifier="exact", amount_low=low, amount_high=high)
            f["status"] = "estimated"
        else:
            values["amount"] = value
            values["qualifier"] = (
                "approximately"
                if lowered.startswith("approximately")
                else "at_least"
                if lowered.startswith("at least")
                else "up_to"
                if lowered.startswith("up to")
                else "exact"
            )
        f["values"] = values
        figures.append(f)
        verification.append(
            {"figure": f["id"], "checked_on": "2026-11-06", "method": "Fixture only."}
        )
    doc["loss_figures"] = figures
    doc["verification"] = verification
    return doc


def write(directory: Path, docs: list[dict[str, Any]]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for d in docs:
        (directory / f"{d['id']}.yaml").write_text(dump(d), encoding="utf-8")
    return directory
