"""Each rule in docs/DESIGN.md section 4.2, broken once, on the fictional fixture."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from cyber_loss_mcp.validation import document

from .conftest import INCIDENT_FIXTURE, TODAY, Validate, dump, error_text

Doc = dict[str, Any]


def test_fixture_is_valid() -> None:
    text = INCIDENT_FIXTURE.read_text(encoding="utf-8")
    issues = document.validate(text, f"incidents/{INCIDENT_FIXTURE.name}", TODAY)
    assert issues == []


def test_round_tripped_fixture_is_valid(incident: Doc, validate_incident: Validate) -> None:
    assert validate_incident(incident) == []


def fig(d: Doc, i: int = 0) -> Doc:
    figure: Doc = d["loss_figures"][i]
    return figure


def src(d: Doc, i: int = 0) -> Doc:
    source: Doc = d["sources"][i]
    return source


def _set(path: str, value: Any) -> Callable[[Doc], None]:
    def mutate(d: Doc) -> None:
        *parents, last = path.split(".")
        node: Any = d
        for p in parents:
            node = node[int(p)] if p.isdigit() else node[p]
        if last.isdigit():
            node[int(last)] = value
        else:
            node[last] = value

    return mutate


def _del(path: str) -> Callable[[Doc], None]:
    def mutate(d: Doc) -> None:
        *parents, last = path.split(".")
        node: Any = d
        for p in parents:
            node = node[int(p)] if p.isdigit() else node[p]
        del node[last]

    return mutate


def _add_figure(d: Doc) -> None:
    extra = dict(fig(d), id="fig-3", values=dict(fig(d)["values"]))
    d["loss_figures"].append(extra)
    d["verification"].append({"figure": "fig-3", "checked_on": "2026-11-06", "method": "x"})


def _later_figure_superseded(d: Doc) -> None:
    _add_figure(d)
    fig(d, 2)["source"] = "src-1"
    fig(d, 2)["quote"] = fig(d, 2)["as_stated"]
    fig(d, 2)["values"]["period_end"] = "2024-01-15"
    fig(d)["values"]["supersedes"] = "fig-3"  # src-2 is later than src-1: fine
    fig(d, 2)["values"]["supersedes"] = "fig-1"  # src-1 is earlier than src-2: wrong


def _point_as_range(d: Doc) -> None:
    values = fig(d)["values"]
    del values["amount"]
    values.update(amount_low="1", amount_high="2")


def _range_as_point(d: Doc) -> None:
    values = fig(d, 1)["values"]
    del values["amount_low"], values["amount_high"]
    values["amount"] = "2000000"


def _superseded_twice(d: Doc) -> None:
    for n in (3, 4):
        extra = dict(fig(d), id=f"fig-{n}", values=dict(fig(d)["values"], supersedes="fig-1"))
        d["loss_figures"].append(extra)
        d["verification"].append({"figure": extra["id"], "checked_on": "2026-11-06", "method": "x"})


def _uncited_source(d: Doc) -> None:
    d["sources"].append(dict(src(d, 1), id="src-3"))


def _company_statement(d: Doc) -> None:
    del src(d)["sec"]
    src(d).update(type="company_statement", url="https://www.example.com/news")


def _regulator_with_sec(d: Doc) -> None:
    src(d)["type"] = "regulator_enforcement"


CASES: list[tuple[str, Callable[[Doc], None], str | None]] = [
    # Schema: shape, required fields and vocabularies.
    ("unknown top-level key", _set("notes", "x"), "Additional properties"),
    ("unknown figure key", _set("loss_figures.0.estimate", True), "Additional properties"),
    ("missing currency", _del("loss_figures.0.currency"), "'currency' is a required property"),
    ("missing quote", _del("loss_figures.0.quote"), "'quote' is a required property"),
    ("missing retrieval date", _del("sources.0.retrieved"), "'retrieved' is a required"),
    ("float amount", _set("loss_figures.0.values.amount", 12300000.0), "is not of type 'string'"),
    ("int amount", _set("loss_figures.0.values.amount", 12300000), "is not of type 'string'"),
    ("negative amount", _set("loss_figures.0.values.amount", "-1"), "does not match"),
    (
        "aggregate type in an incident",
        _set("loss_figures.0.loss_type", "aggregate"),
        "is not one of",
    ),
    ("unknown status", _set("loss_figures.0.status", "disclosed"), "is not one of"),
    ("IC3 source in an incident", _set("sources.0.type", "fbi_ic3_report"), "is not one of"),
    ("Norway problem", _set("incident.country", False), "is not of type 'string'"),
    ("lowercase country", _set("incident.country", "us"), "does not match"),
    ("bad ATT&CK id", _set("techniques.0.id", "T148"), "does not match"),
    ("impossible date", _set("sources.0.published", "2024-02-30"), "is not a 'date'"),
    (
        "amount and range",
        _set("loss_figures.1.values.amount", "1"),
        "is not valid under any of the given schemas",
    ),
    ("quote too long", _set("loss_figures.0.quote", "x" * 301), "is too long"),
    ("wrong profile", _set("profile", "other.yaml"), "was expected"),
    ("markup switched on", _set("inline_markup", "markdown"), "was expected"),
    ("standard missing", _del("standard"), "'standard' is a required"),
    # Amounts against their wording.
    ("amount typo", _set("loss_figures.0.values.amount", "12345678"), "does not equal as_stated"),
    (
        "qualifier mismatch",
        _set("loss_figures.0.values.qualifier", "exact"),
        "reads as 'approximately'",
    ),
    ("currency mismatch", _set("loss_figures.0.currency", "GBP"), "does not read as GBP"),
    ("unaccepted currency", _set("loss_figures.0.currency", "XAU"), "not an accepted"),
    (
        "unreadable wording",
        _set("loss_figures.0.as_stated", "about twelve million dollars"),
        "cannot read",
    ),
    (
        "as_stated not in quote",
        _set("loss_figures.0.quote", "We incurred restoration costs."),
        "verbatim in quote",
    ),
    ("range as reported", _set("loss_figures.1.status", "reported"), "status must be estimated"),
    ("range bounds typo", _set("loss_figures.1.values.amount_high", "5000000"), "do not equal"),
    ("point stored as range", _point_as_range, "so values needs amount"),
    ("range stored as point", _range_as_point, "needs amount_low and amount_high"),
    # References and completeness.
    ("unknown source", _set("loss_figures.0.source", "src-9"), "unknown source 'src-9'"),
    ("uncited source", _set("techniques", []), None),  # src-1 is still the attack-type source
    ("source cited by nothing", _uncited_source, "src-3 is not cited"),
    ("duplicate figure id", _set("loss_figures.1.id", "fig-1"), "duplicate figure id"),
    ("duplicate source id", _set("sources.1.id", "src-1"), "duplicate source id"),
    ("unverified figure", lambda d: d["verification"].pop(), "fig-2 has no verification"),
    ("verification of nothing", _set("verification.1.figure", "fig-7"), "unknown figure 'fig-7'"),
    ("supersedes itself", _set("loss_figures.0.values.supersedes", "fig-1"), "no other figure"),
    (
        "supersedes another type",
        _set("loss_figures.0.values.supersedes", "fig-2"),
        "another loss type",
    ),
    ("supersedes a later figure", _later_figure_superseded, "published later"),
    ("superseded twice", _superseded_twice, "superseded more than once"),
    # Dates.
    ("retrieved before published", _set("sources.0.retrieved", "2024-01-01"), "retrieved before"),
    ("retrieved after updated", _set("updated", "2026-11-05"), "after the record's updated"),
    ("updated in the future", _set("updated", "2026-12-01"), "in the future"),
    (
        "period after source",
        _set("loss_figures.0.values.period_end", "2024-06-30"),
        "period ends after",
    ),
    (
        "period reversed",
        _set("loss_figures.0.values.period_start", "2024-04-01"),
        "after period_end",
    ),
    ("first disclosed wrong", _set("incident.first_disclosed", "2024-01-16"), "earliest source"),
    ("checked before retrieval", _set("sources.1.retrieved", "2026-11-07"), None),
    # URLs.
    (
        "http URL",
        _set("sources.0.url", "http://www.sec.gov/Archives/edgar/data/1/000000000124000001/a.htm"),
        "does not match",
    ),
    (
        "look-alike host",
        _set(
            "sources.0.url",
            "https://www.sec.gov.example.com/Archives/edgar/data/1/000000000124000001/a.htm",
        ),
        "not on the allowlist",
    ),
    (
        "credentials in URL",
        _set(
            "sources.0.url",
            "https://u:p@www.sec.gov/Archives/edgar/data/1/000000000124000001/a.htm",
        ),
        "credentials or a port",
    ),
    (
        "port in URL",
        _set(
            "sources.0.url",
            "https://www.sec.gov:8443/Archives/edgar/data/1/000000000124000001/a.htm",
        ),
        "credentials or a port",
    ),
    ("IP host", _set("sources.0.url", "https://192.0.2.1/x"), "not an IP address"),
    (
        "news site",
        _set("sources.0.url", "https://www.example-news.com/story"),
        "not on the allowlist",
    ),
    (
        "wrong filing in URL",
        _set("sources.0.url", "https://www.sec.gov/Archives/edgar/data/1/000000000124000009/a.htm"),
        "not an EDGAR document in this filing",
    ),
    (
        "EDGAR index not document",
        _set("sources.0.url", "https://www.sec.gov/Archives/edgar/data/1/000000000124000001"),
        "not an EDGAR document",
    ),
    ("SEC filing without ids", _del("sources.0.sec"), "need sec identifiers"),
    (
        "company statement host not listed",
        lambda d: (
            src(d).update(type="company_statement", url="https://www.example.com/news")
            or src(d).pop("sec")
        ),
        "not on the allowlist for company_statement",
    ),
    (
        "regulator source with sec ids",
        lambda d: src(d).update(type="regulator_enforcement"),
        "only sec_filing sources carry sec identifiers",
    ),
    # Text hygiene.
    ("zero-width space", _set("incident.summary", "Example\u200bManufacturing"), "U+200B"),
    ("bidi override", _set("incident.organisation", "Example\u202eInc"), "U+202E"),
    ("control character", _set("incident.summary", "a\x07b"), "U+0007"),
    ("not NFC", _set("incident.organisation", "Cafe\u0301"), "NFC"),
    ("two paragraphs", _set("incident.summary", "One.\n\nTwo."), "spans paragraphs"),
]


@pytest.mark.parametrize(("name", "mutate", "expected"), CASES, ids=[c[0] for c in CASES])
def test_rule(
    incident: Doc,
    validate_incident: Validate,
    name: str,
    mutate: Callable[[Doc], None],
    expected: str | None,
) -> None:
    mutate(incident)
    text = error_text(validate_incident(incident))
    if expected is None:
        if name == "checked before retrieval":
            assert "checked before the source was retrieved" in text
        else:
            assert text == ""
    else:
        assert expected in text, text


def test_filename_must_match_id(incident: Doc) -> None:
    issues = document.validate(dump(incident), "incidents/other.yaml", TODAY)
    assert "file must be named inc-2024-example-manufacturing.yaml" in error_text(issues)


def test_not_a_mapping() -> None:
    assert "must be a YAML mapping" in error_text(document.validate("- a\n", "x.yaml", TODAY))


def test_yaml_error_stops_validation() -> None:
    issues = document.validate("a: [\n", "x.yaml", TODAY)
    assert len(issues) == 1
    assert "YAML error" in issues[0].message
