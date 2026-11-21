"""Tool logic, on the real dataset and on fictional datasets built for each case."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from cyber_loss_mcp import dataset, service
from cyber_loss_mcp import models as m

from . import synthetic
from .conftest import TODAY

# Exact-value regression tests run on a fixed baseline: the first ten incidents, by id.
# Adding records never changes these expectations; correcting one of these ten does,
# deliberately.
BASELINE_IDS = (
    "inc-2017-equifax",
    "inc-2018-british-airways",
    "inc-2021-t-mobile",
    "inc-2022-advanced",
    "inc-2022-dpp-law",
    "inc-2023-23andme",
    "inc-2023-capita",
    "inc-2023-johnson-controls",
    "inc-2023-mgm-resorts",
    "inc-2024-change-healthcare",
)
_FULL = dataset.load()
REAL = dataset.Dataset(
    version=_FULL.version,
    digest=_FULL.digest,
    incidents={k: _FULL.incidents[k] for k in BASELINE_IDS},
)


def ds_of(tmp_path: Path, docs: list[dict[str, Any]]) -> dataset.Dataset:
    return dataset.load(synthetic.write(tmp_path / "data", docs), TODAY)


def figures_in(resp: BaseModel) -> list[m.FigureOut]:
    """Every figure anywhere in a response."""
    out: list[m.FigureOut] = []

    def walk(v: Any) -> None:
        if isinstance(v, m.FigureOut):
            out.append(v)
        elif isinstance(v, BaseModel):
            for name in type(v).model_fields:
                walk(getattr(v, name))
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(resp)
    return out


def assert_envelope(resp: Any) -> None:
    assert resp.disclaimer == m.DISCLAIMER
    assert resp.dataset.digest.startswith("sha256:")
    cited = {(c.incident_id, c.source_id) for c in resp.citations}
    for f in figures_in(resp):
        assert (f.incident_id, f.source_id) in cited, f"{f.incident_id}/{f.figure_id} uncited"


# search_incidents -------------------------------------------------------------------


def test_search_all() -> None:
    r = service.search_incidents(REAL)
    assert r.result.total_matches == 10
    assert_envelope(r)


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"country": "GB"}, 4),
        ({"currency": "GBP"}, 5),
        ({"loss_type": "settlement"}, 2),
        ({"attack_type": "ransomware"}, 3),
        ({"sector": "52"}, 1),
        ({"disclosed_from": 2025}, 4),
        ({"disclosed_to": 2020}, 2),
        ({"currency": "USD", "min_amount": "300000000"}, 3),
        ({"currency": "GBP", "max_amount": "60000"}, 1),
        ({"currency": "USD", "status": "estimated"}, 0),
        ({"country": "FR"}, 0),
    ],
)
def test_search_filters(kwargs: dict[str, Any], expected: int) -> None:
    r = service.search_incidents(REAL, **kwargs)
    assert r.result.total_matches == expected
    assert_envelope(r)


def test_search_figures_shown_match_the_figure_filter() -> None:
    r = service.search_incidents(REAL, loss_type="regulatory_fine", currency="USD")
    assert [i.incident_id for i in r.result.incidents] == ["inc-2017-equifax"]
    assert {f.figure_id for f in r.result.incidents[0].figures} == {"fig-3", "fig-4"}


def test_search_pagination() -> None:
    first = service.search_incidents(REAL, limit=3)
    second = service.search_incidents(REAL, limit=3, offset=3)
    ids = [i.incident_id for i in first.result.incidents + second.result.incidents]
    assert len(set(ids)) == 6
    assert service.search_incidents(REAL, offset=100).result.incidents == []


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"min_amount": "1"}, "needs a currency"),
        ({"currency": "USD", "min_amount": "10", "max_amount": "1"}, "min_amount must not"),
        ({"disclosed_from": 2025, "disclosed_to": 2020}, "disclosed_from must not"),
    ],
)
def test_search_contradictory_input(kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(service.InputError, match=message):
        service.search_incidents(REAL, **kwargs)


def test_amount_filter_skips_ranges(tmp_path: Path) -> None:
    ds = ds_of(
        tmp_path,
        [
            synthetic.incident(
                1, amounts=[("between $1 million and $2 million", "1000000..2000000")]
            )
        ],
    )
    r = service.search_incidents(ds, currency="USD", min_amount="0")
    assert r.result.total_matches == 0
    assert any("range" in n for n in r.result.notes)


# get_incident -----------------------------------------------------------------------


def test_get_incident_is_complete() -> None:
    r = service.get_incident(REAL, "inc-2017-equifax")
    assert [f.amount for f in r.result.figures] == [
        "380500000",
        "180500000",
        "100000000",
        "10000000",
    ]
    assert len(r.result.verification) == 4
    assert {c.url for c in r.citations} == {
        "https://www.sec.gov/Archives/edgar/data/33185/000119312519198584/d734596d8k.htm"
    }
    assert_envelope(r)


def test_get_incident_unknown() -> None:
    with pytest.raises(service.InputError, match="no incident with id"):
        service.get_incident(REAL, "inc-2099-nothing")


# loss_statistics --------------------------------------------------------------------


@pytest.mark.parametrize("group_by", ["sector", "attack_type", "country", "year"])
def test_statistics_each_grouping(group_by: str) -> None:
    r = service.loss_statistics(
        REAL, group_by=group_by, loss_type="regulatory_fine", currency="GBP"
    )
    assert sum(g.n_figures for g in r.result.groups) >= 5
    assert_envelope(r)


def test_statistics_values_and_median_threshold() -> None:
    r = service.loss_statistics(
        REAL, group_by="country", loss_type="regulatory_fine", currency="GBP"
    )
    gb = next(g for g in r.result.groups if g.key == "GB")
    assert (gb.n_figures, gb.n_incidents) == (4, 4)
    assert (gb.min, gb.median, gb.max) == ("60000", "8538160", "20000000")
    us = next(g for g in r.result.groups if g.key == "US")
    assert (us.n_figures, us.median, us.median_note) == (1, None, "median needs at least 3 figures")


def test_statistics_never_pool_status_or_currency() -> None:
    r = service.loss_statistics(
        REAL, group_by="country", loss_type="regulatory_fine", currency="USD"
    )
    assert [(g.key, g.n_figures) for g in r.result.groups] == [("US", 2)]
    assert (
        service.loss_statistics(
            REAL,
            group_by="country",
            loss_type="regulatory_fine",
            currency="GBP",
            status="estimated",
        ).result.groups
        == []
    )


def test_statistics_exclusions_are_listed(tmp_path: Path) -> None:
    doc = synthetic.incident(
        1,
        amounts=[
            ("$1,000,000", "1000000"),
            ("at least $2,000,000", "2000000"),
            ("up to $3,000,000", "3000000"),
            ("$4,000,000", "4000000"),
        ],
    )
    doc["loss_figures"][3]["values"]["supersedes"] = "fig-1"
    estimated = synthetic.incident(
        2, amounts=[("between $1 million and $2 million", "1000000..2000000")]
    )
    ds = ds_of(tmp_path, [doc, estimated])
    r = service.loss_statistics(ds, group_by="country", loss_type="remediation", currency="USD")
    (g,) = r.result.groups
    assert [f.figure_id for f in g.contributors] == ["fig-4"]
    reasons = {e.figure.figure_id: e.reason for e in g.excluded}
    assert reasons == {
        "fig-1": "superseded by fig-4",
        "fig-2": "qualified as at_least, so it is a bound, not a value",
        "fig-3": "qualified as up_to, so it is a bound, not a value",
    }
    est = service.loss_statistics(
        ds, group_by="country", loss_type="remediation", currency="USD", status="estimated"
    )
    (eg,) = est.result.groups
    assert (eg.n_figures, eg.min, eg.excluded[0].reason) == (
        0,
        None,
        "a range, which has no single value to rank",
    )
    assert_envelope(r)


def test_statistics_never_pool_insurance_basis_or_period(tmp_path: Path) -> None:
    ds = ds_of(
        tmp_path,
        [
            synthetic.incident(1, amounts=[("$1,000,000", "1000000")]),
            synthetic.incident(
                2, amounts=[("$2,000,000", "2000000")], insurance_basis="net_of_insurance"
            ),
            synthetic.incident(3, amounts=[("$3,000,000", "3000000")], cumulative=True),
            synthetic.incident(4, amounts=[("$4,000,000", "4000000")]),
        ],
    )
    r = service.loss_statistics(ds, group_by="country", loss_type="remediation", currency="USD")
    groups = {(g.insurance_basis, g.cumulative): g.n_figures for g in r.result.groups}
    assert groups == {("gross", False): 2, ("gross", True): 1, ("net_of_insurance", False): 1}
    assert any("like for like" in n for n in r.result.notes)
    only = service.loss_statistics(
        ds,
        group_by="country",
        loss_type="remediation",
        currency="USD",
        insurance_basis="gross",
        cumulative=False,
    )
    assert [(g.insurance_basis, g.cumulative, g.n_figures) for g in only.result.groups] == [
        ("gross", False, 2)
    ]


def test_statistics_attack_type_groups_overlap(tmp_path: Path) -> None:
    ds = ds_of(tmp_path, [synthetic.incident(1, attack_types=["ransomware", "data_extortion"])])
    r = service.loss_statistics(ds, group_by="attack_type", loss_type="remediation", currency="USD")
    assert [g.key for g in r.result.groups] == ["data_extortion", "ransomware"]
    assert any("several attack types" in n for n in r.result.notes)


def test_statistics_limits_refuse_rather_than_truncate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "MAX_CONTRIBUTORS", 3)
    with pytest.raises(service.InputError, match="never truncated"):
        service.loss_statistics(
            REAL, group_by="country", loss_type="regulatory_fine", currency="GBP"
        )
    monkeypatch.setattr(service, "MAX_GROUPS", 1)
    with pytest.raises(service.InputError, match="groups exceeds"):
        service.loss_statistics(REAL, group_by="year", loss_type="regulatory_fine", currency="GBP")


# estimate_loss_range ----------------------------------------------------------------


def five(tmp_path: Path, extra: list[dict[str, Any]] | None = None) -> dataset.Dataset:
    docs = [synthetic.incident(n, amounts=[(f"${n},000,000", f"{n}000000")]) for n in range(1, 6)]
    return ds_of(tmp_path, docs + (extra or []))


def test_estimate_refuses_below_minimum() -> None:
    r = service.estimate_loss_range(
        REAL, attack_type="ransomware", loss_type="regulatory_fine", currency="GBP"
    )
    assert r.result.outcome == "refused"
    assert (r.result.n, r.result.minimum_comparables) == (2, 5)
    assert r.result.observed is None
    assert r.result.fair_mapping is None
    assert [c.incident_id for c in r.result.comparables] == ["inc-2022-advanced", "inc-2023-capita"]
    assert_envelope(r)


def test_estimate_with_enough_comparables(tmp_path: Path) -> None:
    r = service.estimate_loss_range(
        five(tmp_path), attack_type="ransomware", loss_type="remediation", currency="USD"
    )
    res = r.result
    assert (res.outcome, res.n) == ("estimated", 5)
    assert res.observed == m.Observed(
        min="1000000", p25="2000000", median="3000000", p75="4000000", max="5000000"
    )
    assert res.fair_mapping is not None
    assert (res.fair_mapping.minimum, res.fair_mapping.most_likely, res.fair_mapping.maximum) == (
        "1000000", "3000000", "5000000"
    )  # fmt: skip
    assert any("not the mode" in c for c in res.caveats)
    assert_envelope(r)


def test_estimate_refuses_mixed_bases_and_periods(tmp_path: Path) -> None:
    net = synthetic.incident(
        6, amounts=[("$6,000,000", "6000000")], insurance_basis="net_of_insurance"
    )
    cum = synthetic.incident(7, amounts=[("$7,000,000", "7000000")], cumulative=True)
    ds = five(tmp_path, [net, cum])
    mixed = service.estimate_loss_range(
        ds, attack_type="ransomware", loss_type="remediation", currency="USD"
    )
    assert mixed.result.outcome == "refused"
    assert mixed.result.reason is not None
    assert "5 gross, 1 gross cumulative, 1 net_of_insurance" in mixed.result.reason
    assert mixed.result.observed is None
    chosen = service.estimate_loss_range(
        ds,
        attack_type="ransomware",
        loss_type="remediation",
        currency="USD",
        insurance_basis="gross",
        cumulative=False,
    )
    assert (chosen.result.outcome, chosen.result.n) == ("estimated", 5)
    assert (chosen.result.insurance_basis, chosen.result.cumulative) == ("gross", False)


def test_estimate_never_sums_an_incident(tmp_path: Path) -> None:
    two = synthetic.incident(6, amounts=[("$1,000,000", "1000000"), ("$2,000,000", "2000000")])
    r = service.estimate_loss_range(
        five(tmp_path, [two]), attack_type="ransomware", loss_type="remediation", currency="USD"
    )
    assert r.result.n == 5
    (ex,) = r.result.excluded
    assert ex.incident_id == "inc-2024-synthetic-6"
    assert "not summed" in ex.reason


def test_estimate_excludes_incident_with_only_bounds(tmp_path: Path) -> None:
    bound = synthetic.incident(6, amounts=[("at least $9,000,000", "9000000")])
    r = service.estimate_loss_range(
        five(tmp_path, [bound]), attack_type="ransomware", loss_type="remediation", currency="USD"
    )
    assert r.result.excluded[0].reason.startswith(
        "no eligible figure (fig-1: qualified as at_least"
    )


def test_estimate_filters_narrow_comparables(tmp_path: Path) -> None:
    r = service.estimate_loss_range(
        five(tmp_path),
        attack_type="ransomware",
        loss_type="remediation",
        currency="USD",
        country="GB",
    )
    assert (r.result.outcome, r.result.n) == ("refused", 0)


def test_estimate_year_order_checked() -> None:
    with pytest.raises(service.InputError):
        service.estimate_loss_range(
            REAL,
            attack_type="ransomware",
            loss_type="remediation",
            currency="USD",
            disclosed_from=2025,
            disclosed_to=2024,
        )


def test_full_dataset_tools_run() -> None:
    """Every tool also runs cleanly over the full packaged dataset."""
    assert service.search_incidents(_FULL, limit=50).result.total_matches == len(_FULL.incidents)
    for group_by in ("sector", "attack_type", "country", "year"):
        assert_envelope(
            service.loss_statistics(
                _FULL, group_by=group_by, loss_type="regulatory_fine", currency="USD"
            )
        )
    assert_envelope(service.list_sources(_FULL))


# get_aggregates and list_sources ----------------------------------------------------


def test_aggregates_empty_and_unknown_category() -> None:
    r = service.get_aggregates(REAL)
    assert r.result.aggregates == []
    assert r.citations == []
    with pytest.raises(service.InputError, match="unknown category"):
        service.get_aggregates(REAL, category="bec")


def test_list_sources() -> None:
    r = service.list_sources(REAL)
    res = r.result
    assert (res.incident_count, res.figure_count) == (10, 13)
    assert res.sources_by_type == {"regulator_enforcement": 5, "sec_filing": 5}
    assert res.sources_by_host == {"ico.org.uk": 5, "www.sec.gov": 5}
    assert res.limits.minimum_comparables == service.MIN_COMPARABLES
    assert len(r.citations) == 10
    assert_envelope(r)


ALL: list[Callable[[], BaseModel]] = [
    lambda: service.search_incidents(REAL),
    lambda: service.get_incident(REAL, "inc-2023-capita"),
    lambda: service.loss_statistics(REAL, group_by="year", loss_type="settlement", currency="USD"),
    lambda: service.estimate_loss_range(
        REAL, attack_type="unauthorised_access", loss_type="settlement", currency="USD"
    ),
    lambda: service.get_aggregates(REAL),
    lambda: service.list_sources(REAL),
]


@pytest.mark.parametrize("call", ALL)
def test_every_tool_carries_the_envelope(call: Callable[[], BaseModel]) -> None:
    assert_envelope(call())
