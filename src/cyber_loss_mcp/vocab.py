"""Controlled vocabularies, read from the domain schema so there is one source of truth."""

from __future__ import annotations

import json
from typing import Any, Literal

from .validation import paths

_SCHEMA: dict[str, Any] = json.loads(
    paths.schema_file("incident.schema.json").read_text(encoding="utf-8")
)
_INC = _SCHEMA["properties"]["incident"]["properties"]
_FIG = _SCHEMA["properties"]["loss_figures"]["items"]["properties"]

SECTORS: tuple[str, ...] = tuple(_INC["sector"]["enum"])
ATTACK_TYPES: tuple[str, ...] = tuple(_INC["attack_types"]["items"]["enum"])
LOSS_TYPES: tuple[str, ...] = tuple(_FIG["loss_type"]["enum"])
STATUSES: tuple[str, ...] = tuple(_FIG["status"]["enum"])

# Literal types built from the tuples above, for tool argument schemas.
Sector = Literal[SECTORS]  # type: ignore[valid-type]
AttackType = Literal[ATTACK_TYPES]  # type: ignore[valid-type]
LossType = Literal[LOSS_TYPES]  # type: ignore[valid-type]
Status = Literal[STATUSES]  # type: ignore[valid-type]
GroupBy = Literal["sector", "attack_type", "country", "year"]
