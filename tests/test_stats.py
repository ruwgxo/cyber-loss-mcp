from __future__ import annotations

import statistics
from decimal import Decimal
from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cyber_loss_mcp import stats

D = Decimal


def test_known_values() -> None:
    values = [D(1), D(2), D(3), D(4)]
    assert stats.describe(values) == {
        "min": D(1), "p25": D("1.75"), "median": D("2.5"), "p75": D("3.25"), "max": D(4)
    }  # fmt: skip


def test_odd_count_median_is_middle_value() -> None:
    assert stats.median([D(5), D(1), D(3)]) == D(3)


def test_single_value() -> None:
    assert stats.describe([D(7)]) == dict.fromkeys(["min", "p25", "median", "p75", "max"], D(7))


def test_empty_and_bad_p_are_refused() -> None:
    with pytest.raises(ValueError, match="no values"):
        stats.median([])
    with pytest.raises(ValueError, match="between 0 and 1"):
        stats.quantile([D(1)], D("1.5"))


@pytest.mark.parametrize(
    ("value", "text"),
    [(D("20000000"), "20000000"), (D("2E+7"), "20000000"), (D("2.50"), "2.5"), (D("0"), "0")],
)
def test_fmt_has_no_exponent(value: Decimal, text: str) -> None:
    assert stats.fmt(value) == text


amounts = st.lists(
    st.decimals(min_value=0, max_value=10**12, places=2, allow_nan=False, allow_infinity=False),
    min_size=2,
    max_size=40,
)


@given(amounts)
def test_matches_statistics_inclusive_quantiles(values: list[Decimal]) -> None:
    expected = statistics.quantiles([Fraction(v) for v in values], n=4, method="inclusive")
    d = stats.describe(values)
    assert [Fraction(d["p25"]), Fraction(d["median"]), Fraction(d["p75"])] == expected


@given(amounts)
def test_order_and_permutation_invariance(values: list[Decimal]) -> None:
    d = stats.describe(values)
    assert d["min"] <= d["p25"] <= d["median"] <= d["p75"] <= d["max"]
    assert stats.describe(list(reversed(values))) == d
