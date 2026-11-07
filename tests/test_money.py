from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cyber_loss_mcp.validation import money


@pytest.mark.parametrize(
    ("text", "qualifier", "low", "high", "currency"),
    [
        ("$12.3 million", "exact", "12300000", "12300000", "USD"),
        ("approximately $12.3 million", "approximately", "12300000", "12300000", "USD"),
        ("Approximately $12.3 million", "approximately", "12300000", "12300000", "USD"),
        ("$4,450,000", "exact", "4450000", "4450000", "USD"),
        ("£20m", "exact", "20000000", "20000000", "GBP"),
        ("€1.2 billion", "exact", "1200000000", "1200000000", "EUR"),
        ("US$5 million", "exact", "5000000", "5000000", "USD"),
        ("USD 5 million", "exact", "5000000", "5000000", "USD"),
        ("more than $100 million", "at_least", "100000000", "100000000", "USD"),
        ("up to $50 million", "up_to", "50000000", "50000000", "USD"),
        ("$1.25bn", "exact", "1250000000", "1250000000", "USD"),
        ("$750k", "exact", "750000", "750000", "USD"),
        ("between $10 million and $15 million", "exact", "10000000", "15000000", "USD"),
        ("$10 million to $15 million", "exact", "10000000", "15000000", "USD"),
        ("$10 to $15 million", "exact", "10000000", "15000000", "USD"),
        ("€10-15 million", "exact", "10000000", "15000000", "EUR"),
        ("approximately $1.5\u2013$2 billion", "approximately", "1500000000", "2000000000", "USD"),
        ("$0.5 million", "exact", "500000", "500000", "USD"),
        ("$1,234.56", "exact", "1234.56", "1234.56", "USD"),
    ],
)
def test_parses(text: str, qualifier: str, low: str, high: str, currency: str) -> None:
    parsed = money.parse(text)
    assert parsed.qualifier == qualifier
    assert (parsed.low, parsed.high) == (Decimal(low), Decimal(high))
    assert currency in parsed.currencies


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("12.3 million", "no currency"),
        ("nearly $12.3 million", "cannot read"),
        ("$12.3 million in costs", "cannot read"),
        ("$12.3 millions", "cannot read"),
        ("XYZ 5 million", "unknown currency"),
        (" $5 million", "spaces"),
        ("$5  million", "spaces"),
        ("$15 million to $10 million", "lower to a higher"),
        ("$5 million to $5 million", "lower to a higher"),
        ("at least $1 million to $2 million", "cannot also be qualified"),
        ("$1 million to £2 million", "different currencies"),
        ("$1,23 million", "cannot read"),
        ("", "cannot read"),
    ],
)
def test_rejects(text: str, reason: str) -> None:
    with pytest.raises(money.MoneyError, match=reason):
        money.parse(text)


@given(st.integers(min_value=0, max_value=10**15))
def test_grouped_integers_round_trip(value: int) -> None:
    assert money.parse(f"${value:,}").low == Decimal(value)


@given(st.decimals(min_value=0, max_value=10**6, places=3, allow_nan=False))
def test_millions_are_exact(value: Decimal) -> None:
    assert money.parse(f"£{value} million").low == value * 10**6
