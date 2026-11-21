"""Tool logic as plain functions over a loaded :class:`Dataset`.

The MCP layer in server.py only adapts arguments and errors. Every function here
returns a complete response model, envelope included, so the invariants (citations,
disclaimer, dataset version) are enforced in one place and tested without MCP.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from decimal import Decimal
from urllib.parse import urlsplit

from . import models as m
from . import stats
from .dataset import Dataset, Figure, Incident
from .validation import policy

MAX_SEARCH_RESULTS = 50
MAX_GROUPS = 50
MAX_CONTRIBUTORS = 500
MAX_RESPONSE_BYTES = 256 * 1024
MIN_COMPARABLES = 5
MIN_N_FOR_MEDIAN = 3
POINT_QUALIFIERS = frozenset({"exact", "approximately"})
POOLING_NOTE = (
    "Figures are pooled only when they share an insurance basis (gross, net_of_insurance or "
    "not_stated) and a period type (cumulative over several periods, or a single period): "
    "a gross cost and a cost net of insurance, or a multi-year total and one year's cost, "
    "are not like for like."
)
REPO = "https://github.com/ruwgxo/cyber-loss-mcp"


class InputError(ValueError):
    """The arguments are well-formed but cannot be answered as given."""


# Shared helpers ---------------------------------------------------------------------


def _figure(f: Figure) -> m.FigureOut:
    s = f.source
    return m.FigureOut(
        incident_id=f.incident_id,
        figure_id=f.id,
        loss_type=f.loss_type,
        status=f.status,  # type: ignore[arg-type]
        as_stated=f.as_stated,
        qualifier=f.qualifier,
        currency=f.currency,
        amount=None if f.amount is None else stats.fmt(f.amount),
        amount_low=None if f.amount_low is None else stats.fmt(f.amount_low),
        amount_high=None if f.amount_high is None else stats.fmt(f.amount_high),
        period_start=f.period_start,
        period_end=f.period_end,
        cumulative=f.cumulative,
        insurance_basis=f.insurance_basis,
        supersedes=f.supersedes,
        superseded_by=f.superseded_by,
        locator=f.locator,
        quote=f.quote,
        source_id=s.id,
        source_type=s.type,
        source_url=s.url,
        source_published=s.published,
        source_retrieved=s.retrieved,
    )


def _citations(ds: Dataset, pairs: Iterable[tuple[str, str]]) -> list[m.Citation]:
    """Citations for (incident_id, source_id) pairs, deduplicated, in a stable order."""
    out = []
    for incident_id, source_id in sorted(set(pairs)):
        s = next(x for x in ds.incidents[incident_id].sources if x.id == source_id)
        out.append(
            m.Citation(
                source_id=s.id,
                incident_id=incident_id,
                type=s.type,
                publisher=s.publisher,
                title=s.title,
                url=s.url,
                published=s.published,
                retrieved=s.retrieved,
            )
        )
    return out


def _figure_citations(ds: Dataset, figures: Iterable[m.FigureOut]) -> list[m.Citation]:
    return _citations(ds, ((f.incident_id, f.source_id) for f in figures))


def _info(ds: Dataset) -> m.DatasetInfo:
    return m.DatasetInfo(version=ds.version, digest=ds.digest, record_count=len(ds.incidents))


def _check_years(year_from: int | None, year_to: int | None) -> None:
    if year_from is not None and year_to is not None and year_from > year_to:
        raise InputError("disclosed_from must not be later than disclosed_to")


def _incident_matches(
    inc: Incident,
    *,
    sector: str | None,
    attack_type: str | None,
    country: str | None,
    year_from: int | None,
    year_to: int | None,
) -> bool:
    return (
        (sector is None or inc.sector == sector)
        and (attack_type is None or attack_type in inc.attack_types)
        and (country is None or inc.country == country)
        and (year_from is None or inc.disclosed_year >= year_from)
        and (year_to is None or inc.disclosed_year <= year_to)
    )


def _ineligible(
    f: Figure,
    loss_type: str,
    currency: str,
    status: str,
    *,
    insurance_basis: str | None = None,
    cumulative: bool | None = None,
) -> str | None:
    """Why a figure of the requested kind cannot enter a statistic, or None if it can.
    Figures of another kind are simply not considered and return a sentinel."""
    if (f.loss_type, f.currency, f.status) != (loss_type, currency, status):
        return "other-kind"
    if insurance_basis is not None and f.insurance_basis != insurance_basis:
        return "other-kind"
    if cumulative is not None and f.cumulative != cumulative:
        return "other-kind"
    if f.superseded_by is not None:
        return f"superseded by {f.superseded_by}"
    if f.amount is None:
        return "a range, which has no single value to rank"
    if f.qualifier not in POINT_QUALIFIERS:
        return f"qualified as {f.qualifier}, so it is a bound, not a value"
    return None


# search_incidents -------------------------------------------------------------------


def search_incidents(
    ds: Dataset,
    *,
    sector: str | None = None,
    attack_type: str | None = None,
    country: str | None = None,
    disclosed_from: int | None = None,
    disclosed_to: int | None = None,
    loss_type: str | None = None,
    status: str | None = None,
    currency: str | None = None,
    min_amount: str | None = None,
    max_amount: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> m.SearchResponse:
    _check_years(disclosed_from, disclosed_to)
    lo = Decimal(min_amount) if min_amount is not None else None
    hi = Decimal(max_amount) if max_amount is not None else None
    if (lo is not None or hi is not None) and currency is None:
        raise InputError(
            "an amount filter needs a currency: amounts in different currencies are not comparable"
        )
    if lo is not None and hi is not None and lo > hi:
        raise InputError("min_amount must not be greater than max_amount")
    figure_filtered = any(x is not None for x in (loss_type, status, currency, lo, hi))
    notes: list[str] = []
    if lo is not None or hi is not None:
        notes.append(
            "Amount filters compare single amounts only; figures stated as a range are not "
            "matched by them."
        )

    def figure_ok(f: Figure) -> bool:
        if loss_type is not None and f.loss_type != loss_type:
            return False
        if status is not None and f.status != status:
            return False
        if currency is not None and f.currency != currency:
            return False
        if lo is not None or hi is not None:
            if f.amount is None:
                return False
            if lo is not None and f.amount < lo:
                return False
            if hi is not None and f.amount > hi:
                return False
        return True

    matches: list[tuple[Incident, list[Figure]]] = []
    for inc in ds.sorted_incidents():
        if not _incident_matches(
            inc,
            sector=sector,
            attack_type=attack_type,
            country=country,
            year_from=disclosed_from,
            year_to=disclosed_to,
        ):
            continue
        figs = [f for f in inc.figures if figure_ok(f)]
        if figure_filtered and not figs:
            continue
        matches.append((inc, figs))

    page = matches[offset : offset + limit]
    summaries = []
    shown: list[m.FigureOut] = []
    for inc, figs in page:
        outs = [_figure(f) for f in figs]
        shown += outs
        summaries.append(
            m.IncidentSummary(
                incident_id=inc.id,
                title=inc.title,
                organisation=inc.organisation,
                country=inc.country,
                sector=inc.sector,
                first_disclosed=inc.first_disclosed,
                attack_types=list(inc.attack_types),
                loss_types=sorted({f.loss_type for f in inc.figures}),
                figures=outs,
            )
        )
    if any(f.superseded_by for f in shown):
        notes.append("Some figures are superseded by later ones; see superseded_by.")
    return m.SearchResponse(
        dataset=_info(ds),
        disclaimer=m.DISCLAIMER,
        citations=_figure_citations(ds, shown),
        result=m.SearchResult(
            total_matches=len(matches), offset=offset, limit=limit, incidents=summaries, notes=notes
        ),
    )


# get_incident -----------------------------------------------------------------------


def get_incident(ds: Dataset, incident_id: str) -> m.IncidentResponse:
    inc = ds.incidents.get(incident_id)
    if inc is None:
        raise InputError(f"no incident with id {incident_id!r}; search_incidents lists the ids")
    figures = [_figure(f) for f in inc.figures]
    pairs = {(inc.id, s.id) for s in inc.sources}
    return m.IncidentResponse(
        dataset=_info(ds),
        disclaimer=m.DISCLAIMER,
        citations=_citations(ds, pairs),
        result=m.IncidentDetail(
            incident_id=inc.id,
            title=inc.title,
            updated=inc.updated,
            organisation=inc.organisation,
            organisation_kind=inc.organisation_kind,
            country=inc.country,
            sector=inc.sector,
            sector_basis=inc.sector_basis,
            first_disclosed=inc.first_disclosed,
            attack_types=list(inc.attack_types),
            attack_type_basis=inc.attack_type_basis,
            attack_type_source=inc.attack_type_source,
            summary=inc.summary,
            techniques=[
                m.TechniqueOut(id=t.id, basis=t.basis, source_id=t.source_id)
                for t in inc.techniques
            ],
            figures=figures,
            verification=[
                m.VerificationOut(figure_id=v.figure, checked_on=v.checked_on, method=v.method)
                for v in inc.verification
            ],
        ),
    )


# loss_statistics --------------------------------------------------------------------


def _group_keys(inc: Incident, group_by: str) -> list[str]:
    if group_by == "sector":
        return [inc.sector]
    if group_by == "attack_type":
        return list(inc.attack_types)
    if group_by == "country":
        return [inc.country]
    return [str(inc.disclosed_year)]


def loss_statistics(
    ds: Dataset,
    *,
    group_by: str,
    loss_type: str,
    currency: str,
    status: str = "reported",
    insurance_basis: str | None = None,
    cumulative: bool | None = None,
    sector: str | None = None,
    attack_type: str | None = None,
    country: str | None = None,
    disclosed_from: int | None = None,
    disclosed_to: int | None = None,
) -> m.StatisticsResponse:
    _check_years(disclosed_from, disclosed_to)
    GroupKey = tuple[str, str, bool]
    contributors: dict[GroupKey, list[Figure]] = defaultdict(list)
    excluded: dict[GroupKey, list[tuple[Figure, str]]] = defaultdict(list)
    for inc in ds.sorted_incidents():
        if not _incident_matches(
            inc,
            sector=sector,
            attack_type=attack_type,
            country=country,
            year_from=disclosed_from,
            year_to=disclosed_to,
        ):
            continue
        for f in inc.figures:
            reason = _ineligible(
                f,
                loss_type,
                currency,
                status,
                insurance_basis=insurance_basis,
                cumulative=cumulative,
            )
            if reason == "other-kind":
                continue
            for key in _group_keys(inc, group_by):
                gk = (key, f.insurance_basis, f.cumulative)
                if reason is None:
                    contributors[gk].append(f)
                else:
                    excluded[gk].append((f, reason))

    keys = sorted(set(contributors) | set(excluded))
    if len(keys) > MAX_GROUPS:
        raise InputError(
            f"{len(keys)} groups exceeds the limit of {MAX_GROUPS}; narrow the filters"
        )
    total = sum(len(v) for v in contributors.values())
    if total > MAX_CONTRIBUTORS:
        raise InputError(
            f"{total} contributing figures exceeds the limit of {MAX_CONTRIBUTORS}; narrow the "
            "filters. Results are never truncated, because every contributor must be listed."
        )

    groups = []
    shown: list[m.FigureOut] = []
    for gk in keys:
        key, basis, cum = gk
        figs = contributors.get(gk, [])
        outs = [_figure(f) for f in figs]
        ex = [m.ExcludedFigure(figure=_figure(f), reason=r) for f, r in excluded.get(gk, [])]
        shown += outs + [e.figure for e in ex]
        if not figs:
            groups.append(
                m.Group(
                    key=key,
                    insurance_basis=basis,
                    cumulative=cum,
                    n_figures=0,
                    n_incidents=0,
                    min=None,
                    median=None,
                    median_note="no eligible figures",
                    max=None,
                    contributors=[],
                    excluded=ex,
                )
            )
            continue
        values = [f.amount for f in figs if f.amount is not None]
        enough = len(values) >= MIN_N_FOR_MEDIAN
        groups.append(
            m.Group(
                key=key,
                insurance_basis=basis,
                cumulative=cum,
                n_figures=len(values),
                n_incidents=len({f.incident_id for f in figs}),
                min=stats.fmt(min(values)),
                median=stats.fmt(stats.median(values)) if enough else None,
                median_note=None if enough else f"median needs at least {MIN_N_FOR_MEDIAN} figures",
                max=stats.fmt(max(values)),
                contributors=outs,
                excluded=ex,
            )
        )
    notes = [
        "Statistics count figures; an incident with several eligible figures contributes each "
        "of them, and n_incidents shows how many incidents that is.",
        "Amounts are as disclosed: not converted between currencies, not adjusted for "
        "inflation, and not normalised by organisation size.",
        POOLING_NOTE,
    ]
    if group_by == "attack_type":
        notes.append("An incident with several attack types appears in each of their groups.")
    return m.StatisticsResponse(
        dataset=_info(ds),
        disclaimer=m.DISCLAIMER,
        citations=_figure_citations(ds, shown),
        result=m.StatisticsResult(
            group_by=group_by,
            loss_type=loss_type,
            currency=currency,
            status=status,
            insurance_basis=insurance_basis,
            cumulative=cumulative,
            groups=groups,
            method=(
                "Eligible figures are point amounts qualified exact or approximately, not "
                "superseded, and of the requested loss type, currency and status. The median "
                f"is reported from {MIN_N_FOR_MEDIAN} figures; no mean is computed."
            ),
            notes=notes,
        ),
    )


# estimate_loss_range ----------------------------------------------------------------

CAVEATS = [
    "Disclosed losses are biased upwards: SEC Form 8-K Item 1.05 applies only to material "
    "incidents, and regulators publish only the actions they take.",
    "The FAIR mapping is a convention: the median is used as 'most likely', but the median "
    "is not the mode.",
    "This is a starting point for analyst calibration, not a calibrated estimate.",
    "No currency conversion, inflation adjustment or normalisation by organisation size "
    "has been applied; each comparable shows its year.",
]


def estimate_loss_range(
    ds: Dataset,
    *,
    attack_type: str,
    loss_type: str,
    currency: str,
    insurance_basis: str | None = None,
    cumulative: bool | None = None,
    sector: str | None = None,
    country: str | None = None,
    disclosed_from: int | None = None,
    disclosed_to: int | None = None,
) -> m.EstimateResponse:
    _check_years(disclosed_from, disclosed_to)
    comparables: list[m.Comparable] = []
    excluded: list[m.ExcludedIncident] = []
    values: list[Decimal] = []
    for inc in ds.sorted_incidents():
        if not _incident_matches(
            inc,
            sector=sector,
            attack_type=attack_type,
            country=country,
            year_from=disclosed_from,
            year_to=disclosed_to,
        ):
            continue
        reasons = {
            f.id: _ineligible(
                f,
                loss_type,
                currency,
                "reported",
                insurance_basis=insurance_basis,
                cumulative=cumulative,
            )
            for f in inc.figures
        }
        of_kind = {k: r for k, r in reasons.items() if r != "other-kind"}
        eligible = [f for f in inc.figures if of_kind.get(f.id, "x") is None]
        if not of_kind:
            continue
        if len(eligible) == 1:
            f = eligible[0]
            if f.amount is None:  # pragma: no cover - _ineligible excludes ranges
                continue
            values.append(f.amount)
            comparables.append(
                m.Comparable(
                    incident_id=inc.id,
                    organisation=inc.organisation,
                    first_disclosed=inc.first_disclosed,
                    figure=_figure(f),
                )
            )
        elif len(eligible) > 1:
            excluded.append(
                m.ExcludedIncident(
                    incident_id=inc.id,
                    reason=f"{len(eligible)} eligible figures; they are not summed into a total "
                    "no source disclosed",
                )
            )
        else:
            why = "; ".join(f"{k}: {r}" for k, r in sorted(of_kind.items()))
            excluded.append(
                m.ExcludedIncident(incident_id=inc.id, reason=f"no eligible figure ({why})")
            )

    n = len(values)
    method = (
        "Comparables are incidents matching the filters with exactly one reported, "
        "non-superseded point figure (exact or approximately) of the requested loss type and "
        "currency, all sharing one insurance basis and one period type. Refused below "
        f"{MIN_COMPARABLES} comparables. {stats.QUANTILE_METHOD}"
    )
    observed = fair = None
    reason = None
    mix = Counter((c.figure.insurance_basis, c.figure.cumulative) for c in comparables)
    if len(mix) > 1:
        outcome = "refused"
        parts = ", ".join(
            f"{count} {basis}{' cumulative' if cum else ''}"
            for (basis, cum), count in sorted(mix.items())
        )
        reason = (
            f"The comparables mix insurance bases or period types ({parts}), which are not "
            "like for like. Choose insurance_basis and cumulative to compare one kind."
        )
    elif n < MIN_COMPARABLES:
        outcome = "refused"
        reason = (
            f"{n} comparable incident(s) found; at least {MIN_COMPARABLES} are needed. Widen "
            "the filters (for example drop sector or country) or use loss_statistics."
        )
    else:
        outcome = "estimated"
        d = {k: stats.fmt(v) for k, v in stats.describe(values).items()}
        observed = m.Observed(**d)
        fair = m.FairMapping(
            minimum=d["min"],
            most_likely=d["median"],
            maximum=d["max"],
            note="Observed minimum, median and maximum of the comparables, by convention.",
        )
    shown = [c.figure for c in comparables]
    return m.EstimateResponse(
        dataset=_info(ds),
        disclaimer=m.DISCLAIMER,
        citations=_figure_citations(ds, shown),
        result=m.EstimateResult(
            outcome=outcome,  # type: ignore[arg-type]
            reason=reason,
            n=n,
            minimum_comparables=MIN_COMPARABLES,
            loss_type=loss_type,
            currency=currency,
            insurance_basis=insurance_basis,
            cumulative=cumulative,
            comparables=comparables,
            excluded=excluded,
            observed=observed,
            fair_mapping=fair,
            method=method,
            caveats=CAVEATS,
        ),
    )


# get_aggregates ---------------------------------------------------------------------


def get_aggregates(
    ds: Dataset, *, year: int | None = None, category: str | None = None
) -> m.AggregatesResponse:
    if category is not None:
        raise InputError(
            f"unknown category {category!r}; the dataset holds no aggregate categories yet"
        )
    del year  # no aggregate records exist yet; the filter has nothing to narrow
    return m.AggregatesResponse(
        dataset=_info(ds),
        disclaimer=m.DISCLAIMER,
        citations=[],
        result=m.AggregatesResult(
            aggregates=[],
            notes=[
                "No FBI IC3 aggregate records have been added yet. Aggregates are kept apart "
                "from per-incident figures and will never be mixed into their statistics."
            ],
        ),
    )


# list_sources -----------------------------------------------------------------------


def list_sources(ds: Dataset) -> m.SourcesResponse:
    all_sources = [(inc.id, s) for inc in ds.sorted_incidents() for s in inc.sources]
    by_type = Counter(s.type for _, s in all_sources)
    by_host = Counter((urlsplit(s.url).hostname or "") for _, s in all_sources)
    hosts = {k: sorted(v) for k, v in policy.SOURCE_HOSTS.items()}
    return m.SourcesResponse(
        dataset=_info(ds),
        disclaimer=m.DISCLAIMER,
        citations=_citations(ds, ((i, s.id) for i, s in all_sources)),
        result=m.SourcesResult(
            incident_count=len(ds.incidents),
            figure_count=sum(len(i.figures) for i in ds.incidents.values()),
            sources_by_type=dict(sorted(by_type.items())),
            sources_by_host=dict(sorted(by_host.items())),
            allowed_hosts=hosts,
            source_policy=[
                "Primary public sources only: SEC filings, regulator enforcement records, "
                "court filings and settlements, company statements, and FBI IC3 annual "
                "reports for aggregates only.",
                "No paywalled databases, no scraping against terms of service, and no news "
                "article as the only source of a figure.",
                "Every figure was checked against its source document, which is quoted "
                "verbatim with a locator. Figures that could not be verified are kept out "
                "of the dataset and listed in the unverified log.",
                "Reported and estimated figures are kept apart, as the source frames them.",
            ],
            limits=m.Limits(
                max_search_results=MAX_SEARCH_RESULTS,
                max_groups=MAX_GROUPS,
                max_contributors=MAX_CONTRIBUTORS,
                max_response_bytes=MAX_RESPONSE_BYTES,
                minimum_comparables=MIN_COMPARABLES,
                minimum_n_for_median=MIN_N_FOR_MEDIAN,
            ),
            attack_mapping=(
                "MITRE ATT&CK technique IDs appear only where a source describes the "
                "behaviour, and are checked for format; no ATT&CK release is pinned yet."
            ),
            yaml_markup_standard="2.0.0",
            data_licence="CC-BY-4.0",
            code_licence="MIT",
            corrections_log=f"{REPO}/blob/main/logs/corrections.yaml",
            unverified_log=f"{REPO}/blob/main/logs/unverified.yaml",
            report_an_error=f"{REPO}/issues/new",
        ),
    )
