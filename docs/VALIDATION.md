# Validation

Every dataset file passes four layers of checks before it can be merged. CI runs them on
every pull request. To run them locally from the repository root:

```bash
uv sync
uv run cyber-loss-validate --base-ref origin/main
```

## The four layers

| Layer | Checks | Code |
|---|---|---|
| 1. YAML | Rejects duplicate keys, anchors, aliases, merge keys, explicit tags, unquoted dates and non-string keys. Checks scalar styles: multiline text must be folded (`>`), there must be no literal (`\|`) blocks, and no doubled apostrophes inside block scalars. Also enforces a size cap. | `validation/yamlio.py` |
| 2. Characters | Strings must be Unicode NFC. Control, zero-width, bidirectional-override, private-use and separator characters are rejected, and so is text that spans paragraphs. | `validation/hygiene.py` |
| 3. Schemas | The JSON Schema embedded in YAML Markup Standard 2.0.0. The vendored copy is pinned by SHA-256, and the validator refuses to run if it changes. Then the domain schema for the file (`schemas/*.schema.json`): strict, with no unknown keys and every vocabulary enumerated. | `validation/standard.py`, `validation/document.py` |
| 4. Semantics | Rules no schema can express, listed below. Then the file's profile is applied, every field must be consumed by it, and every block it emits must be a valid standard block. | `validation/incident.py`, `validation/logs.py`, `validation/profile.py` |

### Incident rules

- **Wording and amount agree.**
  - `as_stated` appears verbatim in `quote`.
  - `as_stated` parses under a small, fixed grammar (`validation/money.py`), and its
    amount, qualifier and currency equal `values` exactly.
  - A range must be stored as `amount_low` and `amount_high` with `status: estimated`.
- **References resolve.**
  - Every source, figure and supersession reference points to something in the record.
  - Every source is cited at least once, and every figure has a verification entry.
- **Supersession.** A figure may supersede only an earlier-published figure of the same
  loss type and currency. No figure is superseded twice.
- **Dates.** These orderings must hold:
  - each source is published on or before it is retrieved
  - each source is retrieved on or before the record's `updated` date
  - each figure's period ends on or before its source's publication date
  - each verification is checked on or after its source's retrieval date and on or
    before the record's `updated` date
  - `first_disclosed` equals the earliest source's publication date
  - `updated` is not in the future
- **Source URLs.**
  - The URL uses `https`, with no credentials, port or IP address.
  - The host must match exactly a host listed for that source type in
    `validation/policy.py`. A record cannot add its own hosts.
  - An EDGAR URL must sit under the filer's CIK and the filing's accession number, as
    recorded in `sec`.
- **File name.** The file is named `<id>.yaml`.

### Log rules

- Entries are numbered in order (`unv-1`, `unv-2`, …) and dated in order.
- `supersedes` names an earlier entry, or `none`.
- With `--base-ref`, the entries already on the base branch must be unchanged: a log is
  only ever appended to.

## How the standard's open points are settled

YAML Markup Standard 2.0.0 is a candidate, and its profile grammar leaves some cases
open. The validator settles them as follows. If the standard settles them differently,
the validator changes.

1. **Absent keys.** A path whose key is absent matches nothing. A path that meets the
   wrong type is an error.
2. **Overlap.** Two paths overlap only when they match the same node, so a child path
   (`loss_figures[].values`) may handle fields its parent leaves alone. Two paths that
   consume overlapping data fail.
3. **Missing and non-text fields.** `null` counts as a missing field. A boolean cannot be
   substituted into a template, because the standard doesn't say how it reads.
4. **Empty containers.** Empty lists and mappings contain nothing to consume.
5. **Optional fields.** Templates fail on a missing field, so a template can only
   reference fields that are always present. Optional machine fields therefore live in
   sub-mappings mapped with `visibility: internal`: a figure's `values` and a source's
   `sec`. A figure's exact amount reaches readers through its verbatim `as_stated` and
   `quote`.
6. **Source links.** Records set `inline_markup: none`, so that `$` and `~` in source
   quotes are not read as markup. Link syntax is then unavailable, and the profile shows
   source URLs as plain text, against the standard's style rule on bare URLs. A link
   attribute on a block would fix this in a later revision of the standard.
7. **Body checks.** The standard's semantic check on table row widths applies to `body`
   blocks. Dataset files have no `body`, so it is not implemented.

## Fixtures

`tests/fixtures/inc-2024-example-manufacturing.yaml` is **fictional**: its company,
identifiers and figures are invented to exercise the validator. `tests/test_incident.py`
breaks each rule above once on a copy of it and asserts the expected error.
