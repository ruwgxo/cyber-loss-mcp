"""The bundled dataset, loaded once, validated, and held read-only in memory.

Loading fails closed: if any record fails the same validation CI runs, the server does
not start. Tool arguments never reach this module's file access; records are found by
listing the package's own data directory, and looked up afterwards by id in a dict.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from .validation import document, paths
from .validation.report import errors

DATASET_VERSION = "0.1.0"


class DatasetError(RuntimeError):
    """The bundled data failed validation; the server must not start."""


def _text(value: Any) -> str:
    return str(value).rstrip("\n")


@dataclass(frozen=True, slots=True)
class Source:
    id: str
    type: str
    publisher: str
    title: str
    url: str
    published: str
    retrieved: str


@dataclass(frozen=True, slots=True)
class Figure:
    incident_id: str
    id: str
    as_stated: str
    loss_type: str
    status: str
    currency: str
    insurance_basis: str
    qualifier: str
    amount: Decimal | None
    amount_low: Decimal | None
    amount_high: Decimal | None
    period_start: str | None
    period_end: str
    cumulative: bool
    supersedes: str | None
    superseded_by: str | None
    locator: str
    quote: str
    source: Source


@dataclass(frozen=True, slots=True)
class Technique:
    id: str
    basis: str
    source_id: str


@dataclass(frozen=True, slots=True)
class Verification:
    figure: str
    checked_on: str
    method: str


@dataclass(frozen=True, slots=True)
class Incident:
    id: str
    title: str
    updated: str
    organisation: str
    organisation_kind: str
    country: str
    sector: str
    sector_basis: str
    first_disclosed: str
    attack_types: tuple[str, ...]
    attack_type_basis: str
    attack_type_source: str
    summary: str
    techniques: tuple[Technique, ...]
    figures: tuple[Figure, ...]
    sources: tuple[Source, ...]
    verification: tuple[Verification, ...]

    @property
    def disclosed_year(self) -> int:
        return int(self.first_disclosed[:4])


@dataclass(frozen=True, slots=True)
class Dataset:
    version: str
    digest: str
    incidents: dict[str, Incident]

    def sorted_incidents(self) -> list[Incident]:
        return [self.incidents[k] for k in sorted(self.incidents)]


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _build(doc: dict[str, Any]) -> Incident:
    sources = {
        s["id"]: Source(
            id=s["id"],
            type=s["type"],
            publisher=s["publisher"],
            title=_text(s["title"]),
            url=s["url"],
            published=s["published"],
            retrieved=s["retrieved"],
        )
        for s in doc["sources"]
    }
    superseded_by = {
        f["values"]["supersedes"]: f["id"]
        for f in doc["loss_figures"]
        if "supersedes" in f["values"]
    }
    figures = []
    for f in doc["loss_figures"]:
        v = f["values"]
        figures.append(
            Figure(
                incident_id=doc["id"],
                id=f["id"],
                as_stated=f["as_stated"],
                loss_type=f["loss_type"],
                status=f["status"],
                currency=f["currency"],
                insurance_basis=f["insurance_basis"],
                qualifier=v["qualifier"],
                amount=_decimal(v.get("amount")),
                amount_low=_decimal(v.get("amount_low")),
                amount_high=_decimal(v.get("amount_high")),
                period_start=v.get("period_start"),
                period_end=v["period_end"],
                cumulative=v["cumulative"],
                supersedes=v.get("supersedes"),
                superseded_by=superseded_by.get(f["id"]),
                locator=_text(f["locator"]),
                quote=_text(f["quote"]),
                source=sources[f["source"]],
            )
        )
    inc = doc["incident"]
    return Incident(
        id=doc["id"],
        title=_text(doc["title"]),
        updated=doc["updated"],
        organisation=inc["organisation"],
        organisation_kind=inc["organisation_kind"],
        country=inc["country"],
        sector=inc["sector"],
        sector_basis=_text(inc["sector_basis"]),
        first_disclosed=inc["first_disclosed"],
        attack_types=tuple(inc["attack_types"]),
        attack_type_basis=_text(inc["attack_type_basis"]),
        attack_type_source=inc["attack_type_source"],
        summary=_text(inc["summary"]),
        techniques=tuple(
            Technique(id=t["id"], basis=_text(t["basis"]), source_id=t["source"])
            for t in doc["techniques"]
        ),
        figures=tuple(figures),
        sources=tuple(sources.values()),
        verification=tuple(
            Verification(figure=v["figure"], checked_on=v["checked_on"], method=_text(v["method"]))
            for v in doc["verification"]
        ),
    )


def load(directory: Path | None = None, today: dt.date | None = None) -> Dataset:
    """Load and validate every record in ``directory`` (the packaged data by default)."""
    directory = directory or Path(str(paths.INCIDENTS))
    today = today or dt.datetime.now(dt.UTC).date()
    digest = hashlib.sha256()
    incidents: dict[str, Incident] = {}
    problems: list[str] = []
    for path in sorted(directory.glob("*.yaml")):
        raw = path.read_bytes()
        digest.update(path.name.encode() + b"\0" + raw + b"\0")
        text = raw.decode("utf-8")
        issues = errors(document.validate(text, f"incidents/{path.name}", today))
        if issues:
            problems += [str(i) for i in issues]
            continue
        doc = yaml.safe_load(text)
        incidents[doc["id"]] = _build(doc)
    if problems:
        raise DatasetError("bundled dataset failed validation:\n" + "\n".join(problems))
    return Dataset(
        version=DATASET_VERSION, digest=f"sha256:{digest.hexdigest()}", incidents=incidents
    )
