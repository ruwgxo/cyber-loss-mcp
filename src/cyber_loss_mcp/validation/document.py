"""Validating one dataset file end to end."""

from __future__ import annotations

import datetime as dt
from pathlib import PurePath
from typing import Any

from . import hygiene, incident, logs, paths, profile, standard, yamlio
from .report import Issue, errors

PROFILES = (
    paths.INCIDENT_PROFILE,
    paths.UNVERIFIED_LOG_PROFILE,
    paths.CORRECTIONS_LOG_PROFILE,
)


def _schema_issues(validator_name: str | None, doc: dict[str, Any], file: str) -> list[Issue]:
    validator = (
        standard.root_validator()
        if validator_name is None
        else standard.domain_validator(validator_name)
    )
    label = "YAML Markup Standard 2.0.0" if validator_name is None else validator_name
    out = []
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = ".".join(str(p) for p in err.absolute_path)
        out.append(Issue(file, where, f"{label}: {err.message}"))
    return out


def _load(text: str, file: str) -> tuple[dict[str, Any] | None, list[Issue]]:
    data, issues = yamlio.load(text, file)
    if data is None:
        return None, issues
    if not isinstance(data, dict):
        return None, [*issues, Issue(file, "", "a dataset file must be a YAML mapping")]
    issues += hygiene.check_strings(data, file)
    return data, issues


def load_profile(name: str) -> tuple[dict[str, Any] | None, list[Issue]]:
    file = f"standards/{name}"
    if name not in PROFILES:
        return None, [Issue(file, "", "not one of the dataset's profiles")]
    data, issues = _load(paths.standards_file(name).read_text(encoding="utf-8"), file)
    if data is None:
        return None, issues
    issues += _schema_issues(None, data, file)
    if data.get("record") != "PROFILE":
        issues.append(Issue(file, "record", "a profile must declare record: PROFILE"))
    maps = data.get("maps")
    if isinstance(maps, dict):
        for pattern, templates in maps.items():
            try:
                profile.parse_path(pattern)
            except profile.ProfileError as exc:
                issues.append(Issue(file, f"maps.{pattern}", str(exc)))
            if not isinstance(templates, list) or not all(isinstance(t, dict) for t in templates):
                issues.append(
                    Issue(file, f"maps.{pattern}", "templates must be a list of mappings")
                )
    return (data if not errors(issues) else None), issues


def validate(
    text: str,
    file: str,
    today: dt.date,
    base_text: str | None = None,
) -> list[Issue]:
    """Every issue in one incident record or log, given as text. ``file`` is the path
    used in messages and for the filename rule."""
    doc, issues = _load(text, file)
    if doc is None:
        return issues
    issues += _schema_issues(None, doc, file)

    doc_id = doc.get("id")
    if isinstance(doc_id, str) and doc_id in logs.SCHEMAS:
        domain_issues = _schema_issues(logs.SCHEMAS[doc_id], doc, file)
        issues += domain_issues
        if not domain_issues:
            base = None
            if base_text is not None:
                base, _ = yamlio.load(base_text, f"{file} (base)")
            issues += logs.check(doc, file, base if isinstance(base, dict) else None)
    else:
        domain_issues = _schema_issues(incident.SCHEMA, doc, file)
        issues += domain_issues
        if isinstance(doc_id, str) and PurePath(file).name != f"{doc_id}.yaml":
            issues.append(Issue(file, "id", f"file must be named {doc_id}.yaml"))
        if not domain_issues:
            issues += incident.check(doc, file, today)

    if not domain_issues:
        profile_name = PurePath(str(doc["profile"])).name
        prof, prof_issues = load_profile(profile_name)
        issues += prof_issues
        if prof is not None:
            issues += profile.apply(doc, prof, file).issues
    return issues
