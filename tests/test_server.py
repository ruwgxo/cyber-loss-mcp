"""The MCP layer, exercised through the SDK's own client, in-process."""

from __future__ import annotations

import builtins
import socket
from collections.abc import AsyncIterator
from typing import Any

import pytest
from mcp import Client
from mcp.server import MCPServer
from mcp.types import CallToolResult

from cyber_loss_mcp import dataset, server, service
from cyber_loss_mcp import models as m

DS = dataset.load()
TOOLS = {
    "search_incidents",
    "get_incident",
    "loss_statistics",
    "estimate_loss_range",
    "get_aggregates",
    "list_sources",
}

VALID_CALLS: list[tuple[str, dict[str, Any]]] = [
    ("search_incidents", {"country": "GB", "limit": 2}),
    ("get_incident", {"incident_id": "inc-2018-british-airways"}),
    ("loss_statistics", {"group_by": "country", "loss_type": "regulatory_fine", "currency": "GBP"}),
    (
        "loss_statistics",
        {
            "group_by": "year",
            "loss_type": "incident_costs_total",
            "currency": "USD",
            "insurance_basis": "gross",
            "cumulative": False,
        },
    ),
    (
        "estimate_loss_range",
        {"attack_type": "ransomware", "loss_type": "regulatory_fine", "currency": "GBP"},
    ),
    ("get_aggregates", {}),
    ("list_sources", {}),
]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(params=["auto", "legacy"])
async def client(request: pytest.FixtureRequest) -> AsyncIterator[Client]:
    """A client on the current protocol (2026-07-28) and on the handshake era."""
    async with Client(server.build_server(DS), mode=request.param) as c:
        yield c


def error_text(r: CallToolResult) -> str:
    assert r.is_error
    return " ".join(getattr(c, "text", "") for c in r.content)


@pytest.mark.anyio
async def test_protocol_versions(client: Client) -> None:
    assert client.protocol_version in ("2026-07-28", "2025-11-25")


@pytest.mark.anyio
async def test_tool_list(client: Client) -> None:
    tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == TOOLS
    for t in tools:
        assert t.description
        assert t.input_schema["additionalProperties"] is False, t.name
        assert t.output_schema is not None, t.name
        a = t.annotations
        assert a is not None
        assert (a.read_only_hint, a.destructive_hint, a.open_world_hint) == (True, False, False)


@pytest.mark.anyio
@pytest.mark.parametrize(("name", "args"), VALID_CALLS)
async def test_each_tool_returns_envelope(client: Client, name: str, args: dict[str, Any]) -> None:
    r = await client.call_tool(name, args)
    assert not r.is_error, error_text(r)
    sc = r.structured_content
    assert sc is not None
    assert sc["disclaimer"] == m.DISCLAIMER
    assert sc["dataset"]["digest"] == DS.digest
    # The model reads the text channel: the disclaimer must be there too.
    assert m.DISCLAIMER in r.content[0].text  # type: ignore[union-attr]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("name", "args", "expected"),
    [
        ("search_incidents", {"limit": 5, "unexpected": 1}, "Extra inputs are not permitted"),
        ("search_incidents", {"limit": "5"}, "valid integer"),
        ("search_incidents", {"limit": True}, "valid integer"),
        ("search_incidents", {"limit": 51}, "less than or equal to 50"),
        ("search_incidents", {"limit": 0}, "greater than or equal to 1"),
        ("search_incidents", {"offset": -1}, "greater than or equal to 0"),
        ("search_incidents", {"country": "gb"}, "should match pattern"),
        ("search_incidents", {"country": "GB" * 500}, "at most 2 characters"),
        ("search_incidents", {"sector": "99"}, "Input should be"),
        ("search_incidents", {"currency": "USD", "min_amount": "1e9"}, "should match pattern"),
        ("search_incidents", {"currency": "USD", "min_amount": 5}, "valid string"),
        ("search_incidents", {"disclosed_from": 1800}, "greater than or equal to 1990"),
        ("search_incidents", {"min_amount": "1"}, "needs a currency"),
        ("get_incident", {}, "Field required"),
        ("get_incident", {"incident_id": "../../etc/passwd"}, "should match pattern"),
        (
            "get_incident",
            {"incident_id": "inc-2018-british-airways" + chr(0x202E)},
            "should match pattern",
        ),
        ("get_incident", {"incident_id": "inc-2099-nothing"}, "no incident with id"),
        ("loss_statistics", {"group_by": "sector", "loss_type": "ransom"}, "Field required"),
        (
            "loss_statistics",
            {"group_by": "mean", "loss_type": "ransom", "currency": "USD"},
            "Input should be",
        ),
        (
            "estimate_loss_range",
            {"attack_type": "apt", "loss_type": "ransom", "currency": "USD"},
            "Input should be",
        ),
        (
            "estimate_loss_range",
            {
                "attack_type": "ransomware",
                "loss_type": "ransom",
                "currency": "USD",
                "insurance_basis": "net",
            },
            "Input should be",
        ),
        (
            "loss_statistics",
            {"group_by": "year", "loss_type": "ransom", "currency": "USD", "cumulative": "no"},
            "valid boolean",
        ),
        ("get_aggregates", {"category": "Robert'); DROP TABLE"}, "should match pattern"),
        ("get_aggregates", {"category": "bec"}, "unknown category"),
        ("list_sources", {"verbose": True}, "Extra inputs are not permitted"),
    ],
)
async def test_bad_input_is_a_readable_tool_error(
    client: Client, name: str, args: dict[str, Any], expected: str
) -> None:
    r = await client.call_tool(name, args)
    assert expected in error_text(r)


@pytest.mark.anyio
async def test_empty_result_is_not_an_error(client: Client) -> None:
    r = await client.call_tool("search_incidents", {"country": "FR"})
    assert not r.is_error
    assert r.structured_content is not None
    assert r.structured_content["result"]["incidents"] == []


@pytest.mark.anyio
async def test_refusal_is_a_result_not_an_error(client: Client) -> None:
    r = await client.call_tool(
        "estimate_loss_range",
        {"attack_type": "ransomware", "loss_type": "regulatory_fine", "currency": "GBP"},
    )
    assert not r.is_error
    assert r.structured_content is not None
    assert r.structured_content["result"]["outcome"] == "refused"


@pytest.mark.anyio
async def test_amounts_are_strings_never_numbers(client: Client) -> None:
    r = await client.call_tool("get_incident", {"incident_id": "inc-2017-equifax"})
    assert r.structured_content is not None
    for f in r.structured_content["result"]["figures"]:
        assert isinstance(f["amount"], str)


@pytest.mark.anyio
async def test_rate_limit() -> None:
    limiter = server.RateLimiter(capacity=2, per_second=0.0001)
    async with Client(server.build_server(DS, limiter)) as c:
        for _ in range(2):
            assert not (await c.call_tool("list_sources", {})).is_error
        assert "rate limit exceeded" in error_text(await c.call_tool("list_sources", {}))


@pytest.mark.anyio
async def test_oversized_response_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "MAX_RESPONSE_BYTES", 1000)
    async with Client(server.build_server(DS)) as c:
        assert "over the 1000-byte limit" in error_text(await c.call_tool("list_sources", {}))


@pytest.mark.anyio
async def test_tools_touch_no_network_or_files(monkeypatch: pytest.MonkeyPatch) -> None:
    """The dataset is loaded before this point; no tool call may open a socket or a file."""
    async with Client(server.build_server(DS)) as c:

        def refuse(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError(f"tool attempted I/O: {args!r}")

        monkeypatch.setattr(socket, "socket", refuse)
        monkeypatch.setattr(socket, "create_connection", refuse)
        monkeypatch.setattr(builtins, "open", refuse)
        for name, args in VALID_CALLS:
            r = await c.call_tool(name, args)
            assert not r.is_error, error_text(r)


def test_main_fails_closed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(*_: Any, **__: Any) -> dataset.Dataset:
        raise dataset.DatasetError("bundled dataset failed validation:\nexample")

    monkeypatch.setattr(server, "load", broken)
    assert server.main() == 0 + 1
    assert "failed validation" in capsys.readouterr().err


def test_main_runs_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    ran: list[str] = []
    monkeypatch.setattr(MCPServer, "run", lambda self, transport: ran.append(transport))
    assert server.main() == 0
    assert ran == ["stdio"]


def test_rate_limiter_refills() -> None:
    limiter = server.RateLimiter(capacity=1, per_second=1_000_000)
    assert limiter.take()
    assert limiter.take()
