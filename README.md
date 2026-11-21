# cyber-loss-mcp

A read-only [Model Context Protocol](https://modelcontextprotocol.io) server that gives
AI assistants accurate, sourced figures for the financial losses caused by cyber
incidents.

Every figure in the dataset is tied to the primary public document that disclosed it:

- an SEC filing
- a regulator's enforcement record
- a court filing or settlement
- a company statement
- an FBI IC3 annual report, for aggregates only

Each figure carries the source's own words, a verbatim quote and a locator, so you can
check it yourself in under a minute. Figures the source discloses and figures it
estimates are labelled and never mixed. A figure that can't be checked against its
source isn't included.

> **Status: release candidate.** The dataset holds 25 incidents, each verified against
> its source and checked in CI. Breadth will grow; the verification standard won't
> change.

## Why it exists

Loss figures for cyber incidents get copied from article to article, rounded, and
stripped of their source. This project is the opposite: a small dataset in which
every number can be traced to the document that disclosed it. Its first uses are:

- **Detection ROI:** what attacks cost real organisations.
- **FAIR quantitative risk:** loss-magnitude ranges from comparable incidents, with
  the method and the comparables shown.

## Quick start

You need [uv](https://docs.astral.sh/uv/). `uvx` downloads and builds the package the
first time. After that the server runs locally over stdio. It opens no network port and
makes no network requests: all data ships inside the package.

```bash
uvx --from git+https://github.com/ruwgxo/cyber-loss-mcp cyber-loss-mcp
```

The first launch builds the package, which takes a little longer. After that it starts
in about a second. The command waits for an MCP client on stdin; configure a client
as below rather than running it by hand.

### Claude Code

```bash
claude mcp add cyber-loss -- uvx --from git+https://github.com/ruwgxo/cyber-loss-mcp cyber-loss-mcp
```

### Claude Desktop and other clients

Add this to the client's MCP configuration. For Claude Desktop, that's
`claude_desktop_config.json`.

```json
{
  "mcpServers": {
    "cyber-loss": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/ruwgxo/cyber-loss-mcp", "cyber-loss-mcp"]
    }
  }
}
```

To pin a release, append its tag to the URL, for example `...cyber-loss-mcp@v0.1.0`.

## What it does

| Tool | What it returns |
|---|---|
| `search_incidents` | Incidents filtered by sector, attack type, country, year, loss type, status, currency and amount, with the figures that match. Amount filters need a currency. At most 50 results per page. |
| `get_incident` | One incident in full: every figure with its quote and locator, the basis for its attack type, ATT&CK techniques where a source describes them, verification notes and citations. |
| `loss_statistics` | Figures grouped by sector, attack type, country or year: n, min, median and max per group, never a mean. Lists every contributing figure and every excluded figure with its reason. |
| `estimate_loss_range` | A FAIR-style range from comparable incidents: observed min, quartiles, median and max, with the method, every comparable, n and caveats. **Refuses below 5 comparables**, or when the comparables aren't like for like. |
| `get_aggregates` | FBI IC3 annual aggregates, kept apart from per-incident figures. None added yet. |
| `list_sources` | The dataset's version and digest, sources by type and host, the source policy, limits, licences, and where to report an error. |

Every response carries:

- the dataset version and a SHA-256 digest, so a citation can pin the exact data
- a citation for every figure it contains
- the disclaimer: *figures are as disclosed by the cited source and are not financial
  advice*

Amounts are decimal strings, never JSON numbers, so no client rounds them.

### What the statistics will not do

Statistics compare like with like or refuse. They never:

- **mix currencies:** there is no currency conversion
- **mix reported and estimated figures**
- **mix insurance bases:** gross, net of insurance, and not stated stay apart
- **mix period types:** a cumulative multi-year total never sits beside one year's cost
- **sum an incident's figures** into a total no source disclosed
- **turn a bound into a value:** "at least", "up to" and ranges are excluded and listed
- **adjust for inflation, or normalise by organisation size**
- **compute a mean**

## What it won't do

- **Write anything:** the server is read-only.
- **Fetch URLs at query time:** all data ships with the server; source URLs are
  citations, not links it follows.
- **Execute code, or read files** outside its bundled dataset.
- **Attribute attacks** to threat actors. ATT&CK techniques appear only where a source
  describes the behaviour.
- **Hold personal data:** records are organisation-level, and name no individuals.
- **Give financial, legal or insurance advice.**

## Data provenance policy

Accepted sources are primary and public only:

- SEC EDGAR filings: Form 8-K, 10-K and 10-Q
- regulator enforcement records: SEC, FTC, HHS OCR, UK ICO, EU data protection
  authorities, NYDFS and US state attorneys general
- court filings and settlements, from official court or settlement-administrator sites
- company statements, from the company's own domain
- FBI IC3 annual reports, for aggregates only

Not accepted:

- paywalled databases
- material gathered by scraping against a site's terms of service
- a news article as the only source of a figure

Source hosts are checked against an exact-match allowlist.

Every figure records:

- amount, currency and loss type: ransom, remediation, regulatory fine, settlement,
  revenue impact, incident costs total, or aggregate
- status: reported, or estimated as the source frames it
- qualifier, period and insurance basis
- source URL, type, publication date and retrieval date
- a verbatim quote and a locator

CI checks that the stored amount equals an exact reading of the source's own words.
Figures that can't be verified go to [`logs/unverified.yaml`](logs/unverified.yaml),
never into the dataset. Corrections are appended to
[`logs/corrections.yaml`](logs/corrections.yaml). [docs/VALIDATION.md](docs/VALIDATION.md)
lists every rule, and [docs/DESIGN.md](docs/DESIGN.md) explains the design.

## Reporting a wrong figure

If a figure doesn't match its source, please
[open an issue](https://github.com/ruwgxo/cyber-loss-mcp/issues/new?template=wrong-figure.yml)
with:

1. the incident ID and figure ID
2. what the source actually says, with the page or section

Reported errors take priority over new data. A confirmed error is corrected in a pull
request, recorded in the corrections log, and released under a new dataset version.

## Limitations

- **Small sample.** 25 incidents. `estimate_loss_range` refuses until there are 5
  like-for-like comparables, and on today's data it refuses every query. That is
  correct, not a fault.
- **Disclosure bias.** Disclosed losses skew high. SEC Form 8-K Item 1.05 applies only
  to material incidents, and regulators publish only the actions they take.
- **Source coverage.** Most figures come from SEC filings and UK ICO penalty notices.
  FTC and HHS records are not yet included; their sites block automated retrieval.
- **Figures stated in thousands or millions.** Filings that state figures that way (for
  example "$24" under "Dollars in millions") are not yet supported. Some incidents
  with only such figures are left out.
- **Sector and organisation type.** These are assigned by the maintainer. EDGAR SIC
  codes are used where they exist, and each record says how its sector was assigned.
- **ATT&CK.** Technique IDs are checked for format. No ATT&CK release is pinned yet.
- **Not advice.** The figures describe the past. They are not a forecast for any
  organisation.

## Checking the data yourself

```bash
git clone https://github.com/ruwgxo/cyber-loss-mcp && cd cyber-loss-mcp
uv sync
uv run cyber-loss-validate   # the same checks as CI
uv run pytest                # the test suite
```

## Licence

The code is released under the [MIT License](LICENSE). The dataset, the logs, the YAML
Markup Standard and the profiles are released under [CC BY 4.0](LICENSE-DATA). The
facts themselves, and the source documents cited, are not ours to license. Records
citing the UK ICO contain public sector information licensed under the Open Government
Licence v3.0.
