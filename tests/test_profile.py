from __future__ import annotations

from typing import Any

import pytest

from cyber_loss_mcp.validation import profile
from cyber_loss_mcp.validation.report import Severity

from .conftest import error_text


def apply(
    doc: dict[str, Any], maps: dict[str, Any], unmapped: str = "error"
) -> profile.ProfileResult:
    return profile.apply(doc, {"maps": maps, "unmapped": unmapped}, "f.yaml")


def test_standard_conformance_example() -> None:
    # YAML Markup Standard 2.0.0, conformance_examples: "profile mapping".
    result = apply(
        {"summary": {"text": "Hello."}}, {"summary": [{"block": "prose", "from": "text"}]}
    )
    assert result.blocks == [{"type": "prose", "text": "Hello."}]
    assert result.issues == []


def test_list_items_templates_and_order() -> None:
    doc = {"title": "ignored", "items": [{"id": "a", "n": 1}, {"id": "b", "n": 2}]}
    result = apply(doc, {"items[]": [{"block": "prose", "text": "{id}={n} {{literal}}"}]})
    assert [b["text"] for b in result.blocks] == ["a=1 {literal}", "b=2 {literal}"]
    assert result.issues == []


def test_star_iterates_mapping_values() -> None:
    doc = {"groups": {"x": {"t": "one"}, "y": {"t": "two"}}}
    result = apply(doc, {"groups.*": [{"block": "prose", "from": "t"}]})
    assert [b["text"] for b in result.blocks] == ["one", "two"]


def test_folded_newline_is_dropped() -> None:
    result = apply({"s": {"t": "text\n"}}, {"s": [{"block": "lead", "from": "t"}]})
    assert result.blocks == [{"type": "lead", "text": "text"}]


def test_child_path_and_visibility_only_template() -> None:
    doc = {"f": [{"a": "x", "v": {"secret": 1, "deep": {"k": True}}}]}
    maps = {"f[]": [{"block": "prose", "text": "{a}"}], "f[].v": [{"visibility": "internal"}]}
    result = apply(doc, maps)
    assert result.issues == []
    assert result.blocks == [{"type": "prose", "text": "x"}]


def test_empty_containers_need_no_mapping() -> None:
    assert apply({"t": [], "m": {}}, {}).issues == []


@pytest.mark.parametrize(
    ("doc", "maps", "expected"),
    [
        ({"a": {"x": "1", "y": "2"}}, {"a": [{"block": "prose", "from": "x"}]}, "a.y: not mapped"),
        ({"a": {"x": "1"}}, {}, "a.x: not mapped"),
        ({"a": {"x": "1"}}, {"a": [{"block": "prose", "from": "z"}]}, "missing field 'z'"),
        ({"a": {"x": None}}, {"a": [{"block": "prose", "from": "x"}]}, "missing field 'x'"),
        ({"a": {"x": True}}, {"a": [{"block": "prose", "text": "{x}"}]}, "string or number"),
        ({"a": {"x": "1"}}, {"a": [{"block": "prose", "text": "{x"}]}, "unbalanced brace"),
        ({"a": {"x": "1"}}, {"a": [{"block": "prose", "from": "x", "text": "y"}]}, "both from"),
        ({"a": {"x": "1"}}, {"a": [{"block": "divider", "from": "x"}]}, "takes no from"),
        ({"a": {"x": "1"}}, {"a": [{"text": "{x}"}]}, "needs a block type"),
        ({"a": {"x": "1"}}, {"a": [{"block": "prose", "text": ["no"]}]}, "must be a scalar"),
        ({"a": {"x": "1"}}, {"a[]": [{"visibility": "internal"}]}, "expected a list"),
        ({"a": ["x"]}, {"a.b": [{"visibility": "internal"}]}, "expected a mapping"),
        ({"a": {"x": "1"}}, {"a.b-c": [{"visibility": "internal"}]}, "invalid path segment"),
        ({"a": {"x": "1"}}, {"title": [{"visibility": "internal"}]}, "never mapped"),
        (
            {"a": {"x": "1"}},
            {"a": [{"block": "prose", "from": "x", "colour": "red"}]},
            "invalid block",
        ),
        (
            {"a": {"x": "1"}},
            {"a": [{"block": "heading", "level": 1, "text": "{x}"}]},
            "invalid block",
        ),
        (
            {"a": [{"x": "1"}, {"x": "2"}]},
            {"a[]": [{"block": "heading", "level": 2, "id": "same", "text": "{x}"}]},
            "duplicate id",
        ),
        (
            {"a": {"x": "1"}},
            {"a": [{"visibility": "internal"}], "*": [{"visibility": "internal"}]},
            "matched by both",
        ),
        (
            {"a": {"v": {"x": "1"}}},
            {"a": [{"block": "prose", "text": "{v.x}"}], "a.v": [{"visibility": "internal"}]},
            "handled by both",
        ),
        (
            {"a": {"v": {"x": "1"}}},
            {"a": [{"visibility": "internal"}], "a.v": [{"block": "prose", "from": "x"}]},
            "handled by both",
        ),
    ],
)
def test_errors(doc: dict[str, Any], maps: dict[str, Any], expected: str) -> None:
    assert expected in error_text(apply(doc, maps).issues)


def test_unmapped_warn_mode_downgrades_to_warning() -> None:
    issues = apply({"a": {"x": "1"}}, {}, unmapped="warn").issues
    assert [i.severity for i in issues] == [Severity.WARNING]


def test_parse_path_rejects_empty() -> None:
    with pytest.raises(profile.ProfileError):
        profile.parse_path("")
