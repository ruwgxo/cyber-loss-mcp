"""The vendored YAML Markup Standard 2.0.0 and the JSON Schemas it embeds."""

from __future__ import annotations

import hashlib
import json
from functools import cache
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from . import paths

# Top-level keys the standard reserves for frontmatter and ``meta``. A profile never
# maps these (``profiles.grammar.evaluation``).
RESERVED_KEYS = frozenset(
    {
        "title",
        "updated",
        "subtitle",
        "status",
        "scope",
        "version",
        "tags",
        "authors",
        "language",
        "description",
        "inline_markup",
        "standard",
        "profile",
        "id",
        "meta",
    }
)

# ``profiles.grammar.from_destination``: the block field a template's ``from`` fills.
FROM_DESTINATION = {
    "prose": "text",
    "lead": "text",
    "quote": "text",
    "callout": "text",
    "code": "text",
    "diagram": "text",
    "math": "tex",
    "heading": "text",
    "list": "items",
    "steps": "items",
    "definition": "items",
    "footnotes": "items",
    "table": "rows",
    "fields": "entries",
    "comparison": "criteria",
}


class StandardPinError(RuntimeError):
    """The vendored standard does not match its pinned digest."""


@cache
def standard() -> dict[str, Any]:
    raw = paths.standards_file(paths.STANDARD_FILE).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != paths.STANDARD_SHA256:
        raise StandardPinError(
            f"{paths.STANDARD_FILE} has SHA-256 {digest}, expected {paths.STANDARD_SHA256}"
        )
    data = yaml.safe_load(raw)
    if not isinstance(data, dict) or data.get("version") != "2.0.0":
        raise StandardPinError("vendored standard is not version 2.0.0")
    return data


def _validator(schema: dict[str, Any]) -> Draft202012Validator:
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


@cache
def root_validator() -> Draft202012Validator:
    """Validator for a whole document, profile or book, as the standard defines it."""
    return _validator(standard()["schema"])


@cache
def block_validator() -> Draft202012Validator:
    """Validator for one block, used on the blocks a profile emits."""
    schema = standard()["schema"]
    return _validator({"$ref": "#/$defs/block", "$defs": schema["$defs"]})


@cache
def domain_validator(name: str) -> Draft202012Validator:
    return _validator(json.loads(paths.schema_file(name).read_text(encoding="utf-8")))
