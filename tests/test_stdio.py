"""The installed entry point, launched as a subprocess over stdio, as a client would."""

from __future__ import annotations

import shutil
import sys

import pytest
from mcp import Client, StdioServerParameters


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_entry_point_over_stdio() -> None:
    command = shutil.which("cyber-loss-mcp")
    params = (
        StdioServerParameters(command=command)
        if command
        else StdioServerParameters(command=sys.executable, args=["-m", "cyber_loss_mcp.server"])
    )
    async with Client(params) as client:
        assert client.protocol_version == "2026-07-28"
        r = await client.call_tool("get_incident", {"incident_id": "inc-2023-capita"})
        assert not r.is_error
        assert r.structured_content is not None
        assert r.structured_content["result"]["figures"][0]["as_stated"] == "£14,000,000"
