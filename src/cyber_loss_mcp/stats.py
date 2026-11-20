"""Order statistics in exact decimal arithmetic.

Only the statistics docs/DESIGN.md section 6.4 allows: minimum, maximum, median and
quartiles. There is deliberately no mean, no interpolation beyond the quartile rule
below, and no floating point anywhere.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

QUANTILE_METHOD = (
    "Linear interpolation between closest ranks (Hyndman and Fan type 7, the same as "
    'Python\'s statistics.quantiles(method="inclusive")), computed in exact decimal '
    "arithmetic."
)


def _sorted(values: Sequence[Decimal]) -> list[Decimal]:
    if not values:
        raise ValueError("no values")
    return sorted(values)


def median(values: Sequence[Decimal]) -> Decimal:
    """The middle value, or the mean of the two middle values."""
    s = _sorted(values)
    mid = len(s) // 2
    if len(s) % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


def quantile(values: Sequence[Decimal], p: Decimal) -> Decimal:
    """Type 7 quantile: h = (n - 1) * p, interpolate between floor(h) and the next rank."""
    if not Decimal(0) <= p <= Decimal(1):
        raise ValueError("p must be between 0 and 1")
    s = _sorted(values)
    h = (len(s) - 1) * p
    lo = int(h)
    if lo + 1 >= len(s):
        return s[-1]
    return s[lo] + (h - lo) * (s[lo + 1] - s[lo])


def describe(values: Sequence[Decimal]) -> dict[str, Decimal]:
    s = _sorted(values)
    return {
        "min": s[0],
        "p25": quantile(s, Decimal("0.25")),
        "median": median(s),
        "p75": quantile(s, Decimal("0.75")),
        "max": s[-1],
    }


def fmt(value: Decimal) -> str:
    """A decimal as a plain string: no exponent, no trailing fractional zeros."""
    text = format(value.normalize(), "f")
    return text
