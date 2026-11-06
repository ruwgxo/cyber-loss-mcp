# cyber-loss-mcp design

Status: **draft for review**. Nothing here is built yet. Decisions marked
**Decision needed** are listed together in [section 10](#10-decisions-needed).

## 1. Purpose and non-goals

A read-only MCP server that answers questions about the financial losses caused by
cyber incidents. Every answer comes from a small, hand-verified dataset in which
every figure is tied to the primary public document that disclosed it.

The server will not:

- write, fetch URLs at query time, execute code, or read files outside its bundled
  dataset
- convert currencies, adjust for inflation, fill gaps, or fit distributions. Each of
  these produces numbers no source disclosed.
- attribute incidents to threat actors
- hold personal data about individuals (see [5.6](#56-personal-data))

## 2. Protocol and SDK

Checked on 2026-10-29 against the specification repository, PyPI and npm. Versions
were not taken from memory.

| Item | Current | Evidence |
|---|---|---|
| MCP specification | `2026-07-28` | Latest dated tag in `modelcontextprotocol/modelcontextprotocol`. The previous revision is `2025-11-25`. |
| Python SDK | `mcp` 2.3.0 (2026-10-02) | PyPI. `mcp_types/version.py` lists `2026-07-28` as its modern version and 2024-11-05 to 2025-11-25 as handshake versions. |
| TypeScript SDK | `@modelcontextprotocol/server` 2.3.1 (2026-10-05) | npm. v1 (`@modelcontextprotocol/sdk` 1.32.x) is on a maintenance branch. |

2026-07-28 is a breaking revision. It removes the `initialize` handshake and
protocol sessions, adds a mandatory `server/discover`, and adds a required
`resultType` on every result. Both v2 SDKs handle this and still serve
handshake-era clients, so either language can serve today's clients.

**Recommendation: Python ≥ 3.12 with `mcp` `>=2.3,<3`**, pinned exactly in `uv.lock`.
The reasons:

1. **Exact arithmetic.** Loss figures need exact arithmetic. Python's `decimal` is in
   the standard library. TypeScript would need a third-party decimal library on the
   most correctness-sensitive path.
2. **Scalar-style checks.** The YAML standard requires a check of scalar styles
   (`>` for prose, `|` for code). PyYAML's event stream exposes each scalar's style,
   so this check needs no extra dependency.
3. **Familiarity.** It matches the stack of the `ai-security-mastery` book
   (Python 3.12+), and most security reviewers read Python.
4. **Feature parity.** Neither SDK has a feature the other lacks for a read-only,
   tools-only server.

SDK features used:

- `MCPServer` with Pydantic return models, so every tool publishes an `outputSchema`
  and returns `structuredContent` plus a JSON text copy
- `ToolError` for input and business-logic errors (`isError: true`, which the model
  can read)
- the stdio transport
- tool annotations `readOnlyHint: true`, `openWorldHint: false`,
  `idempotentHint: true`

Annotations are hints that clients must not trust. The guarantees come from the code
and its tests, not from the annotations.

## 3. Repository layout

```
src/cyber_loss_mcp/
  server.py            tool registration, stdio entry point
  models.py            Pydantic models for records and tool I/O
  dataset.py           loads and validates the bundled data at startup, fails closed
  stats.py             Decimal-only order statistics
  tools/               one module per tool
  data/
    incidents/         one YAML record per incident
    aggregates/        FBI IC3 annual figures
schemas/
  incident.schema.json domain schema (JSON Schema 2020-12)
  aggregate.schema.json
standards/
  <the YAML Markup Standard v2.0.0, vendored with a pinned SHA-256>
  <the dataset profile, a PROFILE record mapping domain keys to blocks>
logs/
  unverified.yaml      append-only, never packaged
  corrections.yaml     append-only, packaged
tools/validate.py      CI validator: schema, standard, semantic checks
tests/
docs/
```

The server reads only `cyber_loss_mcp/data`, through `importlib.resources`. It never
builds a path from a tool argument.

## 4. Data schema

### 4.1 How records follow the YAML Markup Standard v2.0.0

- **Domain keys and profile.** Each record is a v2 document with domain keys
  (`incident`, `loss_figures`, `sources`, …) and a declared `profile`. The profile
  maps every key onto standard blocks, so the dataset can also be rendered as a
  readable appendix for either book. The profile uses `unmapped: error`.
- **Frontmatter.** Each record carries `title`, `updated`, `standard: "2.0.0"`, `id`,
  `profile` and `inline_markup: none`. Without `none`, an amount such as
  `$4.5 million … $3 million` would be parsed as inline math, and `~$25m` as
  subscript.
- **Quoting.** All dates and version strings are quoted, so YAML never turns them
  into timestamps or floats.
- **Scalar styles.** Multiline narrative uses `>`. A token-level check enforces this,
  as the standard requires.
- **Strict mode only.** Unknown attributes or blocks fail validation.
- **Append-only logs.** The two logs are append-only documents. A correction is a
  new entry that names the entry it supersedes. Past entries are never edited.

### 4.2 Incident record

All values below are **illustrative placeholders**, not real figures.

```yaml
title: Example Manufacturing ransomware incident, 2024
id: inc-2024-example-manufacturing
updated: '2026-11-02'
standard: '2.0.0'
profile: ../../../standards/<profile file>.yaml
inline_markup: none
meta:
  record_schema: '1.0.0'

incident:
  organisation: Example Manufacturing Inc.
  organisation_kind: public_company       # public_company | private_company | public_body | non_profit
  country: US                             # ISO 3166-1 alpha-2
  sector: '31-33'                         # NAICS 2022 two-digit sector
  sector_basis: EDGAR SIC 3714 mapped to NAICS 31-33
  first_disclosed: '2024-01-15'           # date of the earliest cited source
  attack_types: [ransomware]              # controlled vocabulary, 4.5
  attack_type_basis: >
    The 8-K states that the company "detected ransomware that encrypted
    certain systems".
  attack_type_source: src-1
  techniques:                             # optional; only where a source describes the behaviour
  - id: T1486
    attack_version: '<pinned ATT&CK release>'
    basis: Source describes encryption of systems.
    source: src-1
  summary: >
    One or two neutral sentences, restating only what the sources say.

loss_figures:
- id: fig-1
  loss_type: remediation                  # 4.4
  status: reported                        # reported | estimated, as the source itself frames it
  amount: '12345678'                      # decimal string, whole currency units, never a float
  qualifier: approximately                # exact | approximately | at_least | up_to
  currency: USD                           # ISO 4217
  as_stated: approximately $12.3 million  # verbatim from the source
  period:
    start: '2024-01-01'
    end: '2024-03-31'
    cumulative: true
  insurance_basis: gross                  # gross | net_of_insurance | not_stated
  source: src-2
  locator: Form 10-Q, Part I, Item 2, page 31
  quote: >
    Verbatim excerpt containing the figure, at most 300 characters.
  supersedes: null                        # id of an earlier figure this one replaces

sources:
- id: src-2
  type: sec_filing                        # 4.3
  publisher: Example Manufacturing Inc.
  title: Form 10-Q for the quarter ended 31 March 2024
  url: https://www.sec.gov/Archives/edgar/data/<cik>/<accession>/<doc>.htm
  published: '2024-05-08'
  retrieved: '2026-11-02'
  sec: {form: 10-Q, cik: '0000000000', accession: '0000000000-24-000000'}

verification:
- figure: fig-1
  checked_on: '2026-11-02'
  method: >
    Opened the source URL, found the figure verbatim at the locator, and
    compared amount, currency, period and insurance basis.
```

Rules the validator enforces beyond shape:

- **Required fields.** Every loss figure has amount (or a range, below), currency,
  loss type, status, source (and through it a URL, source type, publication date and
  retrieval date), locator and a verbatim quote. Tool responses repeat the source
  fields inline on every figure.
- **Ranges.** A source that gives a range ("between $X and $Y") is stored as
  `amount_low` and `amount_high` with `status: estimated`. It is never collapsed to a
  midpoint.
- **`as_stated` must match `quote`.** The figure's `as_stated` text must appear
  character for character inside its `quote`, and `amount` must equal `as_stated`
  converted exactly. "$12.3 million" becomes `12300000`; it is never read as
  `12345678`. That conversion is checked mechanically. This is the main defence
  against a typo in `amount`.
- **Dates are ordered.** `retrieved ≥ published`, and a figure's period ends on or
  before its source's publication date.
- **Supersession.** `supersedes` must point to an earlier-published figure of the same
  loss type and currency. Superseded figures stay in the record for audit, but are
  excluded from statistics.
- **Exhaustiveness.** Every figure has a verification entry. Every source is
  referenced by at least one figure or basis.
- **URLs.** `https` only, on a host allowlist (4.3). Exact host match, with no
  user-info, IP literals or ports.
- **Text hygiene.** No control, zero-width or bidirectional-override characters in any
  string. Per-field length caps.

### 4.3 Source types and host allowlist

| `type` | Accepted | Hosts (initial) |
|---|---|---|
| `sec_filing` | 8-K Item 1.05 (and 8.01 or 7.01 where a company discloses there instead), 10-K, 10-Q, and their exhibits | `www.sec.gov` |
| `regulator_enforcement` | SEC, FTC, HHS OCR, UK ICO, EU data protection authorities | `www.sec.gov`, `www.ftc.gov`, `www.hhs.gov`, `ico.org.uk`, `www.edpb.europa.eu` and national DPA domains, added one by one |
| `court_record` | Filings, orders, approved settlements | Court and official settlement-administrator domains, added one by one (**Decision needed**, 10.7) |
| `company_statement` | Statements on the company's own domain, or filed as an SEC exhibit | That company's domain, allowlisted per record |
| `fbi_ic3_report` | IC3 annual reports, **aggregates only** | `www.ic3.gov` |

The policy excludes paywalled databases (including PACER), sources gathered by
scraping against a site's terms of service, and news articles as the only source of
a figure. News may point us to a primary source, but it is never cited.

### 4.4 Loss types

`ransom`, `remediation`, `regulatory_fine`, `settlement`, `revenue_impact`,
`aggregate`, as specified.

- `aggregate` is valid only in aggregate records sourced from `fbi_ic3_report`, and
  never in an incident record. The validator enforces this both ways.
- Filings often disclose one undivided "incident-related costs" figure. That doesn't
  fit the list cleanly (**Decision needed**, 10.5).

### 4.5 Controlled vocabularies

- **`attack_types`.** `ransomware`, `data_extortion` (theft without encryption),
  `business_email_compromise`, `unauthorised_access`, `credential_compromise`,
  `supply_chain_compromise`, `ddos`, `insider`, `misconfiguration_exposure`,
  `not_disclosed`. A value needs a `basis` that cites the source's own words.
  `not_disclosed` is used rather than inference.
- **`techniques`.** Optional ATT&CK IDs, checked against a pinned release of the
  ATT&CK STIX data. They are allowed only when the source describes the behaviour.
  "Ransomware" alone does not imply T1486; the source must say systems were
  encrypted.
- **`sector`.** NAICS 2022 two-digit sectors. For SEC registrants it comes from the
  EDGAR SIC code (recorded in `sector_basis`).

### 4.6 Aggregate record (FBI IC3)

One record per IC3 annual report, with figures by category (for example, business
email compromise losses), each carrying the same source, locator and quote fields. It
records the caveat that IC3 figures are victim-reported losses, not audited losses.
These figures are never mixed with incident figures.

## 5. Source and verification policy

### 5.1 Inclusion

A figure enters the dataset only after someone has:

1. opened the primary document at its URL
2. found the figure at the stated locator
3. copied the quote verbatim
4. recorded the retrieval date
5. completed the verification entry

Nothing is entered from memory, from a secondary summary, or by arithmetic on other
figures.

### 5.2 Unverified log

Anything that fails the inclusion check goes into `logs/unverified.yaml` with:

- the claimed figure
- where it was seen
- why it failed: for example no primary source found, a paywalled source, or a
  figure absent at the locator

This file is never packaged or served.

### 5.3 Reported versus estimated

`status` records how the **source** frames the figure. `estimated` means the source
itself calls it an estimate, projection or range. It never means our estimate.

- Tools filter on status. Statistics never pool reported and estimated figures.
- Every figure in every response carries its status.

### 5.4 Corrections

A wrong figure is fixed in a PR that changes the record and appends an entry to
`logs/corrections.yaml`. The entry records:

- the figure ID
- the old and new values
- who reported it
- the evidence

The dataset version is bumped. `list_sources` reports the correction count, and the
README links to the log.

### 5.5 Versioning and pinning

The dataset has a semantic version and a SHA-256 digest over the canonicalised data
files. Every response includes both, so a figure quoted in either book can cite the
exact dataset state.

### 5.6 Personal data

Records are organisation-level. Proposal for v1: record **no names of individuals**,
even where a filing names them (**Decision needed**, 10.6). No victim or customer
data, ever.

## 6. Tools

### 6.1 Common response envelope

Every tool returns:

```yaml
dataset: {version: '0.1.0', digest: 'sha256:…', record_count: 10}
disclaimer: Figures are as disclosed by the cited source and are not financial advice.
citations:
- {source_id, incident_id, type, publisher, title, url, published, retrieved}
result: {…tool-specific…}
```

Figures inside `result` carry:

- `incident_id`, `figure_id`, `loss_type`, `status`
- `amount`, a string, or `amount_low` and `amount_high`
- `qualifier`, `currency`, `as_stated`, `period`, `insurance_basis`
- `source_id`, plus that source's URL, type, publication date and retrieval date, inline

Amounts are returned as decimal strings, never JSON numbers.

### 6.2 Input handling (all tools)

- **Strict models.** Pydantic models with `extra="forbid"`, enums for every
  vocabulary, bounded integers, and string length caps (IDs ≤ 64, free text not
  accepted at all). If the SDK's generated input schema does not reject unknown
  properties, tools take a single model argument that does. A test proves the
  rejection either way.
- **Bad input is a `ToolError`.** Invalid input, an unknown incident ID, or a
  self-contradictory filter returns `isError: true` with a message the model can act
  on, as the 2026-07-28 spec recommends. Unexpected exceptions return a generic
  error and are logged to stderr. Internals never reach the model.
- **Limits.** Limits are fixed server constants, not arguments, and `list_sources`
  reports them. A result that would exceed a limit is **refused** with a message to
  narrow the filters; it is never silently truncated. A truncated contributor list
  would break the rule that every contributing incident is listed.
- **Rate limit.** An in-process token bucket, generous for interactive use. The spec
  says servers MUST rate-limit tool calls.

### 6.3 Tool list

| Tool | Arguments | Returns | Refuses or errors when |
|---|---|---|---|
| `search_incidents` | `sector`, `attack_type`, `country`, `year_from`, `year_to`, `loss_type`, `status`, `min_amount`, `max_amount`, `currency`, `limit` (≤ 50, default 20), `offset` | Incident summaries: ID, organisation, country, sector, first-disclosed date, attack types, loss types present, and figures matching any amount filter | An amount filter without `currency`; `year_from > year_to`; `min > max`. Empty matches return an empty list, not an error. |
| `get_incident` | `incident_id` (pattern `^inc-\d{4}-[a-z0-9-]{1,48}$`) | Full record: every figure, source, ATT&CK basis and verification entry, plus superseded figures marked as such | Unknown ID (`ToolError`) |
| `loss_statistics` | `group_by` (`sector`, `attack_type`, `country`, `year`), `loss_type` and `currency` (required), `status` (default `reported`), filters as in search | Per group: `n_figures`, `n_incidents`, `min`, `median`, `max`, every contributing figure, and every excluded figure with its reason. No mean. | Over 50 groups or over 500 contributors. Groups with n < 3 report min and max, with `median: null` and a reason. |
| `estimate_loss_range` | `attack_type`, `loss_type`, `currency` (required); `sector`, `country`, `year_from`, `year_to` | Comparables, n, min, p25, median, p75, max, the method text and its caveats | Fewer than 5 eligible comparables. The result is `outcome: refused` with n found, the minimum required, and the comparables found, so the model can widen its filters. |
| `get_aggregates` *(new)* | `year`, `category` (optional) | IC3 aggregate figures with citations | Unknown category (`ToolError`) |
| `list_sources` | none | Dataset version and digest, counts by source type and host, the source policy, limits and thresholds, ATT&CK release, correction count, count of open unverified entries, and the data licence | Never |

`get_aggregates` is added so that IC3 aggregates have a home that cannot mix with
per-incident figures.

### 6.4 Statistics method

The same method serves `loss_statistics` and `estimate_loss_range`.

1. **Eligible figures.** A figure counts only if it is:
   - not superseded
   - the requested loss type, currency and status
   - a point value (no range)
   - qualified `exact` or `approximately`

   `at_least`, `up_to` and range figures are listed under `excluded` with the reason,
   never coerced to a point value.
2. **One per incident (`estimate_loss_range`).** The unit of analysis is the
   incident. An incident with more than one eligible figure of the loss type (for
   example, two separate settlements) is excluded with a reason, not summed. Summing
   would create a total no source disclosed. `loss_statistics` reports both
   `n_figures` and `n_incidents` so this is visible.
3. **Exact arithmetic.** All arithmetic uses `Decimal`. The median is the middle
   value, or the mean of the two middle values. Quartiles use linear interpolation
   between closest ranks (Hyndman and Fan type 7, the same as
   `statistics.quantiles(method="inclusive")`), implemented in `Decimal` and tested
   against hand-computed fixtures.
4. **Nothing is adjusted.** No currency conversion, inflation adjustment,
   normalisation by company size, or distribution fitting. Each contributor shows its
   year so the reader can judge.
5. **FAIR mapping.** The FAIR mapping is labelled a convention: minimum = observed
   min, most likely = observed median, maximum = observed max. The method text
   states:
   - the median is not the mode
   - this is a starting point for analyst calibration, not a calibrated estimate
   - disclosed losses are biased upwards, because 8-K Item 1.05 applies only to
     material incidents and regulators publish only the actions they take
6. **Thresholds.** `MIN_COMPARABLES = 5` and `MIN_N_FOR_MEDIAN = 3` are constants
   reported by `list_sources` (**Decision needed**, 10.11).

## 7. Threat model

Scope: v1 runs locally over **stdio** only, launched by the user's MCP client. No
network listener, no authentication surface. Adding Streamable HTTP later needs its
own review (authorisation per spec, `Origin` validation, request headers).

All data is public, so the main asset is integrity, not confidentiality. The assets
are:

- the dataset's integrity
- the correctness of what reaches the user's model
- the host machine

| # | Threat | Vector | Mitigation |
|---|---|---|---|
| T1 | Wrong or fabricated figure | Authoring error, model hallucination during research, typo | Primary source and verbatim quote required. The `as_stated` match and exact-conversion checks. Verification entries. Your spot-checks. Corrections log. |
| T2 | Poisoned contribution | A PR adds a figure with a plausible but fake source | Host allowlist with exact match. Review of every data PR. An EDGAR accession number required for SEC filings. Optional archive URL. |
| T3 | Hostile tool arguments | A model under prompt injection sends crafted input | Strict models; enums; bounded sizes; no regex, path or query built from input; `ToolError` without internals. Fuzz tests (Hypothesis) over every tool. |
| T4 | Indirect prompt injection through data | Source quotes enter the client's model context | Quotes are short, from official documents, and reviewed. Text hygiene rejects invisible and bidirectional characters. `inline_markup: none`. Data is returned as structured fields. The README tells client authors to treat tool output as data. |
| T5 | Misleading statistics | Small n or pooled categories read as authoritative | No mean. n is always shown. Medians only for n ≥ 3. Refusal below 5 comparables. Reported and estimated never pooled. Mixed currencies refused. Bias caveats in method text. |
| T6 | Resource exhaustion | Large or wide queries | Result and group caps that refuse rather than truncate. Response size cap. Rate limit. The dataset is loaded once and is small. |
| T7 | Unsafe deserialisation or path traversal | YAML loading; a crafted ID | `yaml.safe_load` only. Data is read from package resources at startup and validated, and the server refuses to start if it is invalid. IDs are looked up in a dictionary, never used as paths. |
| T8 | Supply chain | Dependency or CI compromise | Minimal dependencies (`mcp`, `pydantic`, `pyyaml`), locked with hashes. GitHub Actions pinned by SHA with `permissions: contents: read`. Dependabot, `pip-audit`, workflow linting (`zizmor`). Releases via PyPI trusted publishing with attestations, only with your approval. |
| T9 | Overstated tool annotations | — | Annotations describe behaviour; tests prove it: no tool writes, opens sockets or reads outside the package. |

## 8. Licensing

- **Code:** MIT (already in the repo).
- **Data (recommendation):** CC BY 4.0 for the compiled dataset. It covers our
  selection, structure and annotations, and the EU database right. It is compatible
  with a commercial book publisher, and attribution matches the project's ethos.
  ODbL was considered and rejected: its share-alike terms add friction for the
  books. The underlying facts are not ours to license, and source documents are not
  redistributed; we keep URLs and short verbatim quotes. UK ICO material is under
  the Open Government Licence v3.0, which needs an attribution statement in the
  record. Data licence (**Decision needed**, 10.3).

## 9. Test strategy

- **Each tool:**
  - happy path
  - empty result
  - every refusal and `ToolError` path in the table above
  - malformed input: wrong types, unknown properties, out-of-range values, oversized
    strings, Unicode edge cases
  - limit boundaries at the limit and one over
- **Envelope invariant.** A test parametrised over all tools asserts that every
  response has a non-empty `citations` list for every figure it contains, the exact
  disclaimer, the dataset version and the digest.
- **Statistics:**
  - `Decimal` fixtures checked against hand-computed medians and quartiles
  - Hypothesis properties: min ≤ p25 ≤ median ≤ p75 ≤ max; n equals the number of
    listed contributors; results don't depend on input order; no float anywhere
- **Protocol.** In-process client tests through the SDK, at `2026-07-28` and in
  legacy handshake mode (`2025-11-25`): `tools/list` shows annotations and output
  schemas; calls validate against the output schema.
- **Data and standard:**
  - the vendored standard's embedded JSON Schema (on a date-normalised copy)
  - the domain schema
  - profile coverage (every domain key consumed)
  - the scalar-style token pass
  - the semantic rules in 4.2
  - the standard's own `conformance_examples` run as fixtures against our validator
- **Fixture dataset.** Tool tests run against a separate fixture dataset, so that
  adding real incidents never changes expected test values. A second suite checks
  invariants against the real dataset.
- **Negative fixtures.** One deliberately broken record per validation rule, each
  asserted to fail with its expected message.
- **CI** (every PR to `main`):
  - ruff (lint and format)
  - mypy `--strict`
  - pytest with branch coverage ≥ 90% on Python 3.12, 3.13 and 3.14
  - the data validator
  - pip-audit
- **Scheduled link check.** A weekly job checks that source URLs still resolve and
  opens an issue if any don't. It never edits data. This is network access at CI
  time, not at query time.

## 10. Decisions needed

1. **Standard version.** You mentioned v1.0.0; the uploaded file is **2.0.0,
   `status: candidate`**, superseding 1.1.0. I propose targeting 2.0.0 and pinning
   its SHA-256, re-pinning when it is final.
2. **Vendoring the standard.** CI needs it, which means publishing it in this public
   repo under `standards/`. Is that OK, and under what licence?
3. **Data licence.** CC BY 4.0 as recommended?
4. **Filenames.** The standard names records `YYYYMMDD__Title_by_Author.yaml`, with
   the date being the last substantive rewrite. A filename would then change on every
   correction. The server addresses records by `id`, so the API is unaffected either
   way. Options:
   - follow the rule literally
   - treat the dataset like book content with stable names (`incidents/<id>.yaml`)
5. **Undivided cost figures.** Filings often give one undivided "incident-related
   costs" figure. Options:
   - add a loss type such as `incident_costs_total`
   - map these figures to `remediation` with a note

   I recommend adding the type, since `remediation` would overstate what the source
   says.
6. **Names of individuals.** None in v1, even when a filing names someone?
7. **Court records.** PACER is paywalled. Are free official copies acceptable: court
   websites, settlement administrators, and CourtListener's RECAP archive of PACER
   documents? CourtListener is a faithful copy rather than the primary host.
8. **More regulators.** Add US state attorneys general, NYDFS, DOJ and the UK FCA as
   `regulator_enforcement` sources? Several large cyber penalties come from them.
9. **Unverified log location.** In the public repo (helps review, but republishes
   unverified claims) or somewhere private?
10. **Format of this doc.** Markdown here for GitHub review, with all data in YAML
    under your standard. Or should design documents also be YAML records?
11. **Thresholds.** 5 comparables for `estimate_loss_range`, and n ≥ 3 for a median?
12. **Network access for step 2.** This session's network policy blocks every source
    host:
    - `www.sec.gov` and `efts.sec.gov`
    - `www.ftc.gov`
    - `www.hhs.gov`
    - `ico.org.uk`
    - `www.ic3.gov`

    Until they're allowed, I can't open a single source, and I won't enter figures
    I haven't checked. SEC also requires a `User-Agent` with a contact. Which contact
    should I use?

### Issues found in the standard

These are for your own tracking; none blocks this project.

- **A conformance example breaks a validation rule.** The `paragraph segmentation`
  example writes prose with `|-`, which the validation errors list forbids
  ("prose is written as a literal (|) scalar"). One of them should change.
- **Profiles can't build `fields` or `table` blocks from named keys.** Templates
  allow scalar substitution only, so a profile can't project a record's named keys
  into `fields` entries or table rows. The dataset profile will therefore render each
  figure as a heading plus templated prose lines (for example
  `Amount: {as_stated}`). A `fields` entry template in v2.1 would make this cleaner.
- **The filename date changes when records are rewritten.** See decision 4.
