"""Tool output models. Each one is published as the tool's output schema.

Amounts are decimal strings, never JSON numbers, so no client can round them.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DISCLAIMER = "Figures are as disclosed by the cited source and are not financial advice."


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DatasetInfo(_Model):
    version: str
    digest: str = Field(description="SHA-256 over the dataset files, to pin a citation to.")
    record_count: int


class Citation(_Model):
    source_id: str
    incident_id: str
    type: str
    publisher: str
    title: str
    url: str
    published: str
    retrieved: str


class FigureOut(_Model):
    incident_id: str
    figure_id: str
    loss_type: str
    status: Literal["reported", "estimated"]
    as_stated: str = Field(description="The source's own words for the amount.")
    qualifier: str
    currency: str
    amount: str | None = Field(description="Decimal string; null when the source gives a range.")
    amount_low: str | None
    amount_high: str | None
    period_start: str | None
    period_end: str
    cumulative: bool
    insurance_basis: str
    supersedes: str | None
    superseded_by: str | None
    locator: str
    quote: str
    source_id: str
    source_type: str
    source_url: str
    source_published: str
    source_retrieved: str


class ExcludedFigure(_Model):
    figure: FigureOut
    reason: str


class _Envelope(_Model):
    dataset: DatasetInfo
    disclaimer: str
    citations: list[Citation]


# search_incidents -------------------------------------------------------------------


class IncidentSummary(_Model):
    incident_id: str
    title: str
    organisation: str
    country: str
    sector: str
    first_disclosed: str
    attack_types: list[str]
    loss_types: list[str]
    figures: list[FigureOut]


class SearchResult(_Model):
    total_matches: int
    offset: int
    limit: int
    incidents: list[IncidentSummary]
    notes: list[str]


class SearchResponse(_Envelope):
    result: SearchResult


# get_incident -----------------------------------------------------------------------


class TechniqueOut(_Model):
    id: str
    basis: str
    source_id: str


class VerificationOut(_Model):
    figure_id: str
    checked_on: str
    method: str


class IncidentDetail(_Model):
    incident_id: str
    title: str
    updated: str
    organisation: str
    organisation_kind: str
    country: str
    sector: str
    sector_basis: str
    first_disclosed: str
    attack_types: list[str]
    attack_type_basis: str
    attack_type_source: str
    summary: str
    techniques: list[TechniqueOut]
    figures: list[FigureOut]
    verification: list[VerificationOut]


class IncidentResponse(_Envelope):
    result: IncidentDetail


# loss_statistics --------------------------------------------------------------------


class Group(_Model):
    key: str
    n_figures: int
    n_incidents: int
    min: str | None
    median: str | None
    median_note: str | None
    max: str | None
    contributors: list[FigureOut]
    excluded: list[ExcludedFigure]


class StatisticsResult(_Model):
    group_by: str
    loss_type: str
    currency: str
    status: str
    groups: list[Group]
    method: str
    notes: list[str]


class StatisticsResponse(_Envelope):
    result: StatisticsResult


# estimate_loss_range ----------------------------------------------------------------


class Comparable(_Model):
    incident_id: str
    organisation: str
    first_disclosed: str
    figure: FigureOut


class ExcludedIncident(_Model):
    incident_id: str
    reason: str


class Observed(_Model):
    min: str
    p25: str
    median: str
    p75: str
    max: str


class FairMapping(_Model):
    minimum: str
    most_likely: str
    maximum: str
    note: str


class EstimateResult(_Model):
    outcome: Literal["estimated", "refused"]
    reason: str | None
    n: int
    minimum_comparables: int
    loss_type: str
    currency: str
    comparables: list[Comparable]
    excluded: list[ExcludedIncident]
    observed: Observed | None
    fair_mapping: FairMapping | None
    method: str
    caveats: list[str]


class EstimateResponse(_Envelope):
    result: EstimateResult


# get_aggregates ---------------------------------------------------------------------


class AggregatesResult(_Model):
    aggregates: list[FigureOut]
    notes: list[str]


class AggregatesResponse(_Envelope):
    result: AggregatesResult


# list_sources -----------------------------------------------------------------------


class Limits(_Model):
    max_search_results: int
    max_groups: int
    max_contributors: int
    max_response_bytes: int
    minimum_comparables: int
    minimum_n_for_median: int


class SourcesResult(_Model):
    incident_count: int
    figure_count: int
    sources_by_type: dict[str, int]
    sources_by_host: dict[str, int]
    allowed_hosts: dict[str, list[str]]
    source_policy: list[str]
    limits: Limits
    attack_mapping: str
    yaml_markup_standard: str
    data_licence: str
    code_licence: str
    corrections_log: str
    unverified_log: str
    report_an_error: str


class SourcesResponse(_Envelope):
    result: SourcesResult
