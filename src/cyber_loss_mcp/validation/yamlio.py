"""Strict YAML loading for dataset files.

PyYAML's ``safe_load`` already refuses to construct arbitrary objects. On top of that,
dataset files must also be unambiguous to a human reviewer, so this module rejects:

- duplicate mapping keys (PyYAML silently keeps the last one)
- anchors, aliases and merge keys (a value defined in one place and shown in another)
- explicit tags
- non-string mapping keys

A separate pass over the YAML event stream checks scalar styles, which a loaded value
cannot show (YAML Markup Standard 2.0.0, ``scalars.source_validation``).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import yaml

from .report import Issue

MAX_FILE_BYTES = 256 * 1024
_MERGE_TAG = "tag:yaml.org,2002:merge"


class _StrictLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: _StrictLoader, node: yaml.MappingNode) -> dict[str, Any]:
    seen: set[str] = set()
    for key_node, _ in node.value:
        if key_node.tag == _MERGE_TAG:
            raise yaml.constructor.ConstructorError(
                None, None, "merge keys (<<) are not allowed", key_node.start_mark
            )
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str):
            raise yaml.constructor.ConstructorError(
                None, None, f"mapping keys must be strings, found {key!r}", key_node.start_mark
            )
        if key in seen:
            raise yaml.constructor.ConstructorError(
                None, None, f"duplicate key {key!r}", key_node.start_mark
            )
        seen.add(key)
    mapping: dict[str, Any] = yaml.SafeLoader.construct_mapping(loader, node, deep=True)  # type: ignore[assignment]
    return mapping


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def _style_issues(text: str, file: str) -> list[Issue]:
    issues: list[Issue] = []
    for event in yaml.parse(text, Loader=yaml.SafeLoader):
        line = f"line {event.start_mark.line + 1}" if event.start_mark else ""
        if isinstance(event, yaml.AliasEvent):
            issues.append(Issue(file, line, "aliases are not allowed"))
            continue
        if isinstance(event, yaml.NodeEvent) and event.anchor is not None:
            issues.append(Issue(file, line, "anchors are not allowed"))
        if isinstance(event, (yaml.ScalarEvent, yaml.SequenceStartEvent, yaml.MappingStartEvent)):
            implicit = event.implicit
            explicit_tag = event.tag is not None and (
                not any(implicit) if isinstance(implicit, tuple) else not implicit
            )
            if explicit_tag:
                issues.append(Issue(file, line, f"explicit tag {event.tag} is not allowed"))
        if not isinstance(event, yaml.ScalarEvent):
            continue
        multiline = bool(
            event.start_mark and event.end_mark and event.end_mark.line > event.start_mark.line
        )
        if event.style == "|":
            issues.append(
                Issue(
                    file,
                    line,
                    "literal block scalar (|): dataset files hold no code, diagram or math, "
                    "so multiline text must be folded (>)",
                )
            )
        elif multiline and event.style != ">":
            issues.append(Issue(file, line, "multiline text must be a folded block scalar (>)"))
        elif event.style == ">" and "''" in event.value:
            issues.append(
                Issue(
                    file,
                    line,
                    "doubled apostrophe ('') inside a block scalar renders as two characters",
                )
            )
    return issues


def _date_issues(value: Any, file: str, where: str = "") -> list[Issue]:
    """Unquoted dates load as date objects. Dataset dates must be quoted ISO strings."""
    if isinstance(value, (dt.date, dt.datetime)):
        return [Issue(file, where, "dates must be quoted strings such as '2024-01-31'")]
    if isinstance(value, dict):
        out: list[Issue] = []
        for k, v in value.items():
            out += _date_issues(v, file, f"{where}.{k}" if where else k)
        return out
    if isinstance(value, list):
        out = []
        for i, v in enumerate(value):
            out += _date_issues(v, file, f"{where}[{i}]")
        return out
    return []


def load(text: str, file: str) -> tuple[Any, list[Issue]]:
    """Parse ``text``. Returns the loaded value, or ``None`` when parsing failed, and
    every issue found."""
    if len(text.encode("utf-8")) > MAX_FILE_BYTES:
        return None, [Issue(file, "", f"file is larger than {MAX_FILE_BYTES} bytes")]
    try:
        issues = _style_issues(text, file)
        data = yaml.load(text, Loader=_StrictLoader)  # noqa: S506 - strict SafeLoader subclass
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark or exc.context_mark
        where = f"line {mark.line + 1}" if mark else ""
        return None, [Issue(file, where, f"YAML error: {exc.problem or exc}")]
    except yaml.YAMLError as exc:
        return None, [Issue(file, "", f"YAML error: {exc}")]
    issues += _date_issues(data, file)
    return data, issues
