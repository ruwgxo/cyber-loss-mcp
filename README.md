# cyber-loss-mcp

A read-only [Model Context Protocol](https://modelcontextprotocol.io) server that
gives AI assistants accurate, sourced data on the financial losses caused by cyber
incidents.

Every loss figure in the dataset is tied to a primary public source: an SEC filing,
a regulator's enforcement record, a court filing or settlement, a company
statement, or, for aggregates only, the FBI IC3 annual report. Figures the
source discloses and figures that are estimates are kept apart and labelled.
A figure that can't be checked against its source isn't included.

> **Status: design phase.** There is no server code or data in this repository
> yet. The sections below describe the intended behaviour. They will be updated
> as each part lands and is verified.

## Why it exists

Loss figures for cyber incidents get copied from article to article, rounded,
and stripped of their source. This project is meant to be the opposite: a small
dataset in which every number can be traced back to the document that
disclosed it. Its first uses are:

- **Detection ROI**: what an undetected or late-detected attack cost real
  organisations.
- **FAIR quantitative risk**: loss-magnitude ranges built from comparable
  incidents, with the method and the comparables shown.

Correctness comes before coverage. The dataset starts small (25–50 incidents,
each checked against its sources) and grows only at that standard.

## What it will do

| Tool | Purpose |
|---|---|
| `search_incidents` | Filter incidents by sector, attack type, year, country and loss range |
| `get_incident` | Return a full incident record with every citation |
| `loss_statistics` | Return grouped statistics (n, median, range) and list every contributing incident |
| `list_sources` | Describe the dataset's provenance and source policy |
| `estimate_loss_range` | Return a FAIR-style loss range from comparable incidents, with its method, comparables and n. It refuses when there are too few comparables |

Every response carries its citations and a one-line disclaimer: figures are as
disclosed by the source and are not financial advice.

The tool list is provisional until the design doc is approved.

## What it won't do

- **Write anything.** The server is read-only. No tool modifies data.
- **Fetch URLs at query time.** All data ships with the server. Source URLs are
  returned as citations, not followed.
- **Execute code or read files** outside its bundled dataset.
- **Present estimates as disclosed figures**, or round, extrapolate or fill
  gaps in what a source says.
- **Attribute attacks** to threat actors or speculate about attribution.
  MITRE ATT&CK mappings appear only where the source supports them.
- **Hold personal data** beyond what an official filing names, and only where
  it's relevant.
- **Act as financial, legal or insurance advice.**

## Data provenance policy

Accepted sources (primary and public only):

- SEC EDGAR filings: Form 8-K Item 1.05, 10-K and 10-Q
- Regulator enforcement records: SEC, FTC, HHS OCR, UK ICO, EU data
  protection authorities
- Court filings and settlements
- Company statements
- FBI IC3 annual reports, for aggregate figures only

Not accepted: paywalled databases, scraping against a site's terms of service,
or a news article as the only source for a figure.

Each loss figure records its amount, currency, loss type (ransom, remediation,
regulatory fine, settlement, revenue impact or aggregate), status (reported or
estimated), primary source URL, source type, publication date and retrieval
date. A figure that can't be verified from its source goes into an unverified
log for review, not into the dataset.

## Reporting a wrong figure

If a figure doesn't match its source, or its source doesn't support it, please
[open an issue](https://github.com/ruwgxo/cyber-loss-mcp/issues/new) with:

1. the incident ID and the figure in question
2. what the source actually says, with a link and page or section reference.

Reported errors take priority over new data.

## Licence

The code is released under the [MIT License](LICENSE). The licence for the
dataset will be set out in the design doc before any data is added.
