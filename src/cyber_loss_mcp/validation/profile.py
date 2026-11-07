"""Applying a profile (YAML Markup Standard 2.0.0, ``profiles``) to a document.

The profile grammar leaves a few cases open. This implementation settles them as
follows, and docs/VALIDATION.md records each choice:

- A path whose key is absent matches nothing. A path that meets the wrong type (``[]``
  on a mapping, a key on a list) is an error.
- Paths overlap only when two paths match the same node. A child path such as
  ``loss_figures[].values`` may handle a field its parent path's templates leave alone.
- Data is handled twice, and so fails, when two paths consume overlapping fields
  (through ``from``, a ``{field}`` or a visibility-only template), or when one path
  consumes a node that another path also matches.
- A ``{field}`` must be a string or number. ``null`` counts as missing, and booleans are
  refused, because the standard does not say how either should read.
- Empty lists and mappings contain nothing to consume.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from . import standard
from .report import Issue, Severity

NodePath = tuple[str | int, ...]

_SEGMENT = re.compile(r"^(?:\*|[A-Za-z_][A-Za-z0-9_]*(?:\[\])?)$")
_PLACEHOLDER = re.compile(r"\{\{|\}\}|\{([^{}]*)\}")


class ProfileError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _Segment:
    key: str | None  # None means *
    each: bool  # key[]


def parse_path(path: str) -> list[_Segment]:
    if not path:
        raise ProfileError("empty path")
    out: list[_Segment] = []
    for raw in path.split("."):
        if not _SEGMENT.match(raw):
            raise ProfileError(f"invalid path segment {raw!r} in {path!r}")
        if raw == "*":
            out.append(_Segment(None, each=False))
        elif raw.endswith("[]"):
            out.append(_Segment(raw[:-2], each=True))
        else:
            out.append(_Segment(raw, each=False))
    return out


def _resolve(root: dict[str, Any], path: str) -> list[tuple[NodePath, Any]]:
    current: list[tuple[NodePath, Any]] = [((), root)]
    for seg in parse_path(path):
        nxt: list[tuple[NodePath, Any]] = []
        for node_path, value in current:
            if not isinstance(value, dict):
                raise ProfileError(f"{path!r}: expected a mapping at {_fmt(node_path)}")
            if seg.key is None:
                nxt += [((*node_path, k), v) for k, v in value.items()]
                continue
            if seg.key not in value:
                continue
            child, child_path = value[seg.key], (*node_path, seg.key)
            if seg.each:
                if not isinstance(child, list):
                    raise ProfileError(f"{path!r}: expected a list at {_fmt(child_path)}")
                nxt += [((*child_path, i), item) for i, item in enumerate(child)]
            else:
                nxt.append((child_path, child))
        current = nxt
    return current


def _fmt(node_path: NodePath) -> str:
    out = ""
    for part in node_path:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else part)
    return out or "(root)"


def _lookup(item: Any, dotted: str) -> tuple[Any, NodePath]:
    value: Any = item
    rel: NodePath = ()
    for key in dotted.split("."):
        if not isinstance(value, dict) or key not in value or value[key] is None:
            raise ProfileError(f"missing field {dotted!r}")
        value, rel = value[key], (*rel, key)
    return value, rel


def _clean(value: Any) -> Any:
    """Folded scalars end with a newline the reader never sees."""
    if isinstance(value, str):
        return value.rstrip("\n")
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


@dataclass
class ProfileResult:
    blocks: list[dict[str, Any]] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


@dataclass
class _State:
    file: str
    result: ProfileResult
    matched: dict[NodePath, str] = field(default_factory=dict)
    consumed: list[tuple[NodePath, str]] = field(default_factory=list)

    def error(self, where: str, message: str) -> None:
        self.result.issues.append(Issue(self.file, where, message))


def _substitute(text: str, item: Any, item_path: NodePath, state: _State, pattern: str) -> str:
    def repl(match: re.Match[str]) -> str:
        matched = match.group(0)
        if matched == "{{":
            return "{"
        if matched == "}}":
            return "}"
        value, rel = _lookup(item, match.group(1))
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ProfileError(f"{{{match.group(1)}}} must be a string or number")
        state.consumed.append(((*item_path, *rel), pattern))
        return str(_clean(value))

    out = _PLACEHOLDER.sub(repl, text)
    leftover = _PLACEHOLDER.sub("", text)
    if "{" in leftover or "}" in leftover:
        raise ProfileError(f"unbalanced brace in template {text!r}")
    return out


def _emit(
    template: dict[str, Any], item: Any, item_path: NodePath, state: _State, pattern: str
) -> dict[str, Any] | None:
    if set(template) == {"visibility"}:
        state.consumed.append((item_path, pattern))
        return None
    block_type = template.get("block")
    if not isinstance(block_type, str):
        raise ProfileError("template needs a block type, or visibility only")
    block: dict[str, Any] = {"type": block_type}
    for key, value in template.items():
        if key in ("block", "from"):
            continue
        if isinstance(value, str):
            block[key] = _substitute(value, item, item_path, state, pattern)
        elif isinstance(value, (bool, int, float)):
            block[key] = value
        else:
            raise ProfileError(f"template attribute {key!r} must be a scalar")
    if "from" in template:
        dest = standard.FROM_DESTINATION.get(block_type)
        if dest is None:
            raise ProfileError(f"block {block_type!r} takes no from")
        if dest in block:
            raise ProfileError(f"{block_type}: both from and an explicit {dest!r}")
        value, rel = _lookup(item, str(template["from"]))
        block[dest] = _clean(value)
        state.consumed.append(((*item_path, *rel), pattern))
    return block


def _leaves(value: Any, node_path: NodePath) -> list[NodePath]:
    if isinstance(value, dict):
        return [leaf for k, v in value.items() for leaf in _leaves(v, (*node_path, k))]
    if isinstance(value, list):
        return [leaf for i, v in enumerate(value) for leaf in _leaves(v, (*node_path, i))]
    return [node_path]


def _is_prefix(a: NodePath, b: NodePath) -> bool:
    return b[: len(a)] == a


def apply(document: dict[str, Any], profile: dict[str, Any], file: str) -> ProfileResult:
    """Map ``document``'s domain keys onto blocks. Every unhandled field is an issue."""
    state = _State(file, ProfileResult())
    domain = {k: v for k, v in document.items() if k not in standard.RESERVED_KEYS}
    maps = profile.get("maps", {})
    for pattern, templates in maps.items():
        try:
            if parse_path(pattern)[0].key in standard.RESERVED_KEYS:
                raise ProfileError("frontmatter and meta are never mapped")
            matches = _resolve(domain, pattern)
        except ProfileError as exc:
            state.error(pattern, f"profile path: {exc}")
            continue
        for node_path, item in matches:
            if node_path in state.matched:
                state.error(
                    _fmt(node_path),
                    f"matched by both {state.matched[node_path]!r} and {pattern!r}",
                )
                continue
            state.matched[node_path] = pattern
            for template in templates:
                try:
                    block = _emit(template, item, node_path, state, pattern)
                except ProfileError as exc:
                    state.error(_fmt(node_path), f"{pattern}: {exc}")
                    continue
                if block is not None:
                    state.result.blocks.append(block)

    _check_overlaps(state)

    consumed = [p for p, _ in state.consumed]
    severity = Severity.WARNING if profile.get("unmapped") == "warn" else Severity.ERROR
    for leaf in _leaves(domain, ()):
        if not any(_is_prefix(p, leaf) for p in consumed):
            state.result.issues.append(
                Issue(file, _fmt(leaf), "not mapped by the profile", severity)
            )

    _check_blocks(state)
    return state.result


def _check_overlaps(state: _State) -> None:
    """Two paths may not handle the same data: neither by both consuming overlapping
    fields, nor by one consuming a node that another path also maps."""
    reported: set[NodePath] = set()

    def report(node_path: NodePath, a: str, b: str) -> None:
        if node_path not in reported:
            reported.add(node_path)
            state.error(_fmt(node_path), f"handled by both {a!r} and {b!r}")

    for i, (c1, p1) in enumerate(state.consumed):
        for c2, p2 in state.consumed[i + 1 :]:
            if p1 != p2 and (_is_prefix(c1, c2) or _is_prefix(c2, c1)):
                report(max(c1, c2, key=len), p1, p2)
        for matched_path, other in state.matched.items():
            if other != p1 and _is_prefix(c1, matched_path):
                report(matched_path, p1, other)


def _check_blocks(state: _State) -> None:
    seen: set[str] = set()
    validator = standard.block_validator()
    for index, block in enumerate(state.result.blocks):
        where = f"emitted block {index} ({block.get('type')})"
        for err in validator.iter_errors(block):
            state.error(where, f"invalid block: {err.message}")
        block_id = block.get("id")
        if isinstance(block_id, str):
            if block_id in seen:
                state.error(where, f"duplicate id {block_id!r}")
            seen.add(block_id)
