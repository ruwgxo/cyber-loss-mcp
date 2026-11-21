# Changelog

All notable changes to this project are recorded here. Versions follow
[Semantic Versioning](https://semver.org/). The dataset has its own version, reported
by every tool response, and changes to it are listed here too.

## 0.1.0rc1

First release candidate. Package version 0.1.0rc1; dataset version 0.1.0.

### Server

- Six read-only tools over stdio: `search_incidents`, `get_incident`,
  `loss_statistics`, `estimate_loss_range`, `get_aggregates` and `list_sources`.
- Built on the MCP Python SDK 2.3 and protocol revision 2026-07-28. Clients using the
  older `initialize` handshake are also served.
- Strict arguments. Unknown arguments, type coercion and out-of-range values are
  rejected as tool errors.
- Every response carries the dataset version and digest, citations for every figure,
  and the disclaimer.
- Statistics never pool:
  - currencies
  - reported with estimated figures
  - insurance bases
  - cumulative with single-period figures
- `estimate_loss_range` refuses below 5 like-for-like comparables.
- The dataset is validated at startup, and the server won't start if it is invalid.
- Rate limit and response size cap.

### Dataset 0.1.0

- 25 incidents and 34 figures, from:
  - SEC filings
  - SEC enforcement press releases
  - UK ICO penalty notices
- Every figure is checked in CI. Its stored amount must equal an exact reading of the
  source's own words, and its source host must be on the allowlist.
- One figure is held in the unverified log: Marriott's ICO penalty, which awaits a
  maintainer reading of the original notice.

### Validation

- `cyber-loss-validate` checks, in order:
  - strict YAML
  - character hygiene
  - the YAML Markup Standard 2.0.0 schema
  - the domain schemas
  - the semantic rules
  - profile coverage
  - that logs are only appended to
