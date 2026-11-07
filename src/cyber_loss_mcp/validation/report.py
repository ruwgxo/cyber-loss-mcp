"""Validation findings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class Issue:
    """One validation finding. ``where`` is a dotted path inside the document, or a
    ``line N`` location for findings from the YAML token pass."""

    file: str
    where: str
    message: str
    severity: Severity = Severity.ERROR

    def __str__(self) -> str:
        loc = f"{self.file}: {self.where}" if self.where else self.file
        return f"{self.severity}: {loc}: {self.message}"


def errors(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity is Severity.ERROR]
