"""Semantic rules for the append-only logs (YAML Markup Standard 2.0.0,
``append_only_documents``)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from .report import Issue

SCHEMAS = {
    "unverified-log": "unverified_log.schema.json",
    "corrections-log": "corrections_log.schema.json",
}


def check(doc: dict[str, Any], file: str, base: dict[str, Any] | None) -> list[Issue]:
    """``base`` is the same log on the branch being merged into, when there is one."""
    issues: list[Issue] = []
    prefix = {"unverified-log": "unv", "corrections-log": "cor"}[doc["id"]]
    entries = doc["entries"]
    last: dt.date | None = None
    for n, entry in enumerate(entries, start=1):
        where = f"entries[{n - 1}]"
        if entry["id"] != f"{prefix}-{n}":
            issues.append(
                Issue(file, where, f"entries are numbered in order; expected {prefix}-{n}")
            )
        date = dt.date.fromisoformat(entry["date"])
        if last and date < last:
            issues.append(Issue(file, where, "entries must be in date order"))
        last = date
        target = entry["supersedes"]
        if target != "none":
            earlier = {e["id"] for e in entries[: n - 1]}
            if target not in earlier:
                issues.append(
                    Issue(file, where, f"supersedes {target}, which is not an earlier entry")
                )
    if last and dt.date.fromisoformat(doc["updated"]) < last:
        issues.append(Issue(file, "updated", "is earlier than the last entry"))
    if base is not None:
        old = base.get("entries")
        if not isinstance(old, list) or entries[: len(old)] != old:
            issues.append(
                Issue(
                    file,
                    "entries",
                    "existing entries were edited, removed or reordered; the log is append-only",
                )
            )
    return issues
