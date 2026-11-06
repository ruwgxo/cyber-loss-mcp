"""Semantic rules for incident records (docs/DESIGN.md, section 4.2)."""

from __future__ import annotations

import datetime as dt
import ipaddress
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from . import money, policy
from .hygiene import text
from .report import Issue

SCHEMA = "incident.schema.json"


def _date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def _check_url(url: str, source_type: str, incident_id: str) -> str | None:
    parts = urlsplit(url)
    if parts.scheme != "https":
        return "source URLs must use https"
    if parts.username or parts.password or parts.port is not None:
        return "source URLs must not carry credentials or a port"
    host = (parts.hostname or "").lower()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return "source URLs must use a host name, not an IP address"
    if source_type == "company_statement":
        allowed = policy.COMPANY_HOSTS.get(incident_id, frozenset())
    else:
        allowed = policy.SOURCE_HOSTS.get(source_type, frozenset())
    if host not in allowed:
        return f"host {host!r} is not on the allowlist for {source_type} sources"
    return None


def _check_sec(source: dict[str, Any]) -> str | None:
    """An EDGAR document URL names the filer's CIK and the filing's accession number.
    Both must match the identifiers recorded with the source."""
    sec = source.get("sec")
    if source["type"] != "sec_filing":
        return "only sec_filing sources carry sec identifiers" if sec else None
    if not sec:
        return "sec_filing sources need sec identifiers (form, cik, accession)"
    path = urlsplit(source["url"]).path.split("/")
    expected = [
        "",
        "Archives",
        "edgar",
        "data",
        str(int(sec["cik"])),
        sec["accession"].replace("-", ""),
    ]
    if path[: len(expected)] != expected or len(path) <= len(expected):
        return (
            "URL is not an EDGAR document in this filing: expected "
            f"https://www.sec.gov{'/'.join(expected)}/<document>"
        )
    return None


def _check_amount(fig: dict[str, Any]) -> list[str]:
    values = fig["values"]
    try:
        parsed = money.parse(fig["as_stated"])
    except money.MoneyError as exc:
        return [f"as_stated: {exc}"]
    problems: list[str] = []
    if fig["currency"] not in policy.CURRENCIES:
        problems.append(f"currency {fig['currency']!r} is not an accepted ISO 4217 code")
    if fig["currency"] not in parsed.currencies:
        problems.append(f"as_stated does not read as {fig['currency']}")
    if parsed.qualifier != values["qualifier"]:
        problems.append(
            f"values.qualifier is {values['qualifier']!r} but as_stated reads as "
            f"{parsed.qualifier!r}"
        )
    if parsed.is_range:
        if "amount" in values:
            problems.append("as_stated is a range, so values needs amount_low and amount_high")
        elif (Decimal(values["amount_low"]), Decimal(values["amount_high"])) != (
            parsed.low,
            parsed.high,
        ):
            problems.append(
                f"amount_low/amount_high do not equal as_stated ({parsed.low} to {parsed.high})"
            )
        if fig["status"] != "estimated":
            problems.append("a range is an estimate: status must be estimated")
    elif "amount" not in values:
        problems.append("as_stated is a single amount, so values needs amount")
    elif Decimal(values["amount"]) != parsed.low:
        problems.append(f"values.amount {values['amount']} does not equal as_stated ({parsed.low})")
    return problems


def check(doc: dict[str, Any], file: str, today: dt.date) -> list[Issue]:  # noqa: PLR0915
    """Rules a JSON Schema cannot express. Assumes ``doc`` already passed the schema."""
    issues: list[Issue] = []

    def err(where: str, message: str) -> None:
        issues.append(Issue(file, where, message))

    incident_id = doc["id"]
    sources = {s["id"]: s for s in doc["sources"]}
    figures = {f["id"]: f for f in doc["loss_figures"]}
    if len(sources) != len(doc["sources"]):
        err("sources", "duplicate source id")
    if len(figures) != len(doc["loss_figures"]):
        err("loss_figures", "duplicate figure id")

    referenced: set[str] = set()

    def ref(where: str, source_id: str) -> dict[str, Any] | None:
        referenced.add(source_id)
        if source_id not in sources:
            err(where, f"unknown source {source_id!r}")
            return None
        source: dict[str, Any] = sources[source_id]
        return source

    updated = _date(doc["updated"])
    if updated > today + dt.timedelta(days=1):
        err("updated", "date is in the future")

    for i, s in enumerate(doc["sources"]):
        where = f"sources[{i}]"
        published, retrieved = _date(s["published"]), _date(s["retrieved"])
        if retrieved < published:
            err(where, "retrieved before published")
        if retrieved > updated:
            err(where, "retrieved after the record's updated date")
        for problem in (_check_url(s["url"], s["type"], incident_id), _check_sec(s)):
            if problem:
                err(f"{where}.url", problem)

    inc = doc["incident"]
    ref("incident.attack_type_source", inc["attack_type_source"])
    for i, t in enumerate(doc["techniques"]):
        ref(f"techniques[{i}].source", t["source"])

    for i, fig in enumerate(doc["loss_figures"]):
        where = f"loss_figures[{i}]"
        source = ref(f"{where}.source", fig["source"])
        if text(fig["as_stated"]) not in text(fig["quote"]):
            err(where, "as_stated does not appear verbatim in quote")
        for problem in _check_amount(fig):
            err(where, problem)
        values = fig["values"]
        end = _date(values["period_end"])
        if "period_start" in values and _date(values["period_start"]) > end:
            err(f"{where}.values", "period_start is after period_end")
        if source and end > _date(source["published"]):
            err(f"{where}.values", "period ends after the source was published")
        target_id = values.get("supersedes")
        if target_id is not None:
            target = figures.get(target_id)
            if target is None or target_id == fig["id"]:
                err(f"{where}.values.supersedes", f"no other figure {target_id!r}")
            elif (target["loss_type"], target["currency"]) != (fig["loss_type"], fig["currency"]):
                err(
                    f"{where}.values.supersedes",
                    "superseded figure has another loss type or currency",
                )
            elif (
                source
                and target["source"] in sources
                and _date(sources[target["source"]]["published"]) > _date(source["published"])
            ):
                err(f"{where}.values.supersedes", "superseded figure was published later")

    superseded = [
        f["values"]["supersedes"] for f in doc["loss_figures"] if "supersedes" in f["values"]
    ]
    if len(superseded) != len(set(superseded)):
        err("loss_figures", "a figure is superseded more than once")

    published_dates = [_date(s["published"]) for s in doc["sources"]]
    if _date(inc["first_disclosed"]) != min(published_dates):
        err("incident.first_disclosed", "must equal the publication date of the earliest source")

    checked: set[str] = set()
    for i, v in enumerate(doc["verification"]):
        where = f"verification[{i}]"
        fig = figures.get(v["figure"])
        if fig is None:
            err(where, f"unknown figure {v['figure']!r}")
            continue
        checked.add(v["figure"])
        src = sources.get(fig["source"])
        if src and _date(v["checked_on"]) < _date(src["retrieved"]):
            err(where, "checked before the source was retrieved")
        if _date(v["checked_on"]) > updated:
            err(where, "checked after the record's updated date")
    for fig_id in figures.keys() - checked:
        err("verification", f"figure {fig_id} has no verification entry")
    for source_id in sources.keys() - referenced:
        err("sources", f"source {source_id} is not cited by any figure or basis")
    return issues
