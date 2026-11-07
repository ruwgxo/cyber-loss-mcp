"""Locations of the files bundled with the package."""

from __future__ import annotations

from importlib.resources import files
from importlib.resources.abc import Traversable

PACKAGE = files("cyber_loss_mcp")
STANDARDS = PACKAGE / "standards"
SCHEMAS = PACKAGE / "schemas"
INCIDENTS = PACKAGE / "data" / "incidents"

STANDARD_FILE = "20261016__YAML_Markup_Standard_v2_by_Raghav_Dinesh.yaml"
# SHA-256 of the vendored standard. Changing the standard means changing this pin in the
# same reviewed commit.
STANDARD_SHA256 = "5b981fe73d28583cf8edcb68600216d369011307c38401caf8e30bb2e08682dc"

INCIDENT_PROFILE = "20261106__Cyber_Loss_Incident_Profile_by_Raghav_Dinesh.yaml"
UNVERIFIED_LOG_PROFILE = "20261106__Cyber_Loss_Unverified_Log_Profile_by_Raghav_Dinesh.yaml"
CORRECTIONS_LOG_PROFILE = "20261106__Cyber_Loss_Corrections_Log_Profile_by_Raghav_Dinesh.yaml"


def standards_file(name: str) -> Traversable:
    return STANDARDS / name


def schema_file(name: str) -> Traversable:
    return SCHEMAS / name
