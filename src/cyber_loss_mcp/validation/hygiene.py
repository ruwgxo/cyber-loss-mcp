"""Character-level checks on every string in a dataset file."""

from __future__ import annotations

import unicodedata
from typing import Any

from .report import Issue

# Control (Cc, except newline), format (Cf: zero-width and bidirectional controls),
# private-use, surrogate and line/paragraph separator characters.
_BANNED_CATEGORIES = frozenset({"Cc", "Cf", "Co", "Cs", "Zl", "Zp"})


def _check(text: str) -> str | None:
    if not unicodedata.is_normalized("NFC", text):
        return "text is not in Unicode NFC form"
    body = text[:-1] if text.endswith("\n") else text
    if "\n" in body:
        return "text spans paragraphs; dataset text is one paragraph"
    for ch in body:
        if unicodedata.category(ch) in _BANNED_CATEGORIES:
            return f"disallowed character U+{ord(ch):04X} ({unicodedata.category(ch)})"
    return None


def check_strings(value: Any, file: str, where: str = "") -> list[Issue]:
    if isinstance(value, str):
        problem = _check(value)
        return [Issue(file, where, problem)] if problem else []
    out: list[Issue] = []
    if isinstance(value, dict):
        for k, v in value.items():
            out += check_strings(k, file, where)
            out += check_strings(v, file, f"{where}.{k}" if where else str(k))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out += check_strings(v, file, f"{where}[{i}]")
    return out


def text(value: Any) -> str:
    """A loaded string as the reader sees it: without a folded scalar's final newline."""
    return value.rstrip("\n") if isinstance(value, str) else ""
