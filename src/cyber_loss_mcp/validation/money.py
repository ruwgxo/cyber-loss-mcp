"""Parsing a figure's ``as_stated`` text into an exact amount.

The dataset stores each amount twice: as the source's own words (``as_stated``) and as
a decimal string (``values.amount``). The validator parses the words and requires the two
to agree exactly, so a typo in either one fails CI.

The parser accepts a deliberately small grammar. Text outside it is rejected, never
guessed at; extend the grammar in a reviewed change when a source needs it.

    as_stated := [qualifier " "] money
               | [qualifier " "] "between " money " and " money
               | [qualifier " "] money (" to " | "-" | en dash | " " en dash " ") money
    money     := currency number [multiplier]

In a range, the first amount takes the second's multiplier when it has none of its own
("$10 to $15 million" is 10,000,000 to 15,000,000), and the second takes the first's
currency when it has none ("€10-15 million").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from . import policy

_QUALIFIERS = {
    "approximately": "approximately",
    "about": "approximately",
    "around": "approximately",
    "roughly": "approximately",
    "at least": "at_least",
    "more than": "at_least",
    "over": "at_least",
    "in excess of": "at_least",
    "exceeding": "at_least",
    "up to": "up_to",
    "as much as": "up_to",
    "no more than": "up_to",
    "less than": "up_to",
}
_MULTIPLIERS = {
    "thousand": Decimal(10**3),
    "k": Decimal(10**3),
    "million": Decimal(10**6),
    "m": Decimal(10**6),
    "billion": Decimal(10**9),
    "bn": Decimal(10**9),
}

_CURRENCY = r"(?:US\$|C\$|A\$|NZ\$|S\$|HK\$|\$|£|€|¥|[A-Z]{3} )"
_NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_MULT = r"(?: (?:thousand|million|billion)|(?:k|m|bn))"


def _money(name: str) -> str:
    return rf"(?P<{name}_cur>{_CURRENCY})?(?P<{name}_num>{_NUMBER})(?P<{name}_mul>{_MULT})?"


_QUAL = "|".join(sorted((re.escape(q) for q in _QUALIFIERS), key=len, reverse=True))
_POINT = re.compile(rf"(?:(?P<qual>{_QUAL}) )?{_money('a')}", re.IGNORECASE)
_BETWEEN = re.compile(rf"(?:(?P<qual>{_QUAL}) )?between {_money('a')} and {_money('b')}", re.I)
_SPAN = re.compile(
    rf"(?:(?P<qual>{_QUAL}) )?{_money('a')}(?: to |-|\u2013| \u2013 ){_money('b')}", re.I
)


class MoneyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Money:
    qualifier: str  # exact | approximately | at_least | up_to
    currencies: frozenset[str]  # currencies the stated symbol or code allows
    low: Decimal
    high: Decimal  # equal to low for a point amount

    @property
    def is_range(self) -> bool:
        return self.low != self.high


def _currencies(token: str | None) -> frozenset[str]:
    if token is None:
        raise MoneyError("the amount has no currency symbol or code")
    token = token.strip()
    if token in policy.CURRENCY_SYMBOLS:
        return policy.CURRENCY_SYMBOLS[token]
    if token in policy.CURRENCIES:
        return frozenset({token})
    raise MoneyError(f"unknown currency {token!r}")


def _amount(num: str, mul: str | None) -> Decimal:
    value = Decimal(num.replace(",", ""))
    if mul:
        value *= _MULTIPLIERS[mul.strip().lower()]
    return value


def parse(text: str) -> Money:
    """Parse ``text`` or raise :class:`MoneyError`."""
    if text != text.strip() or "  " in text:
        raise MoneyError("as_stated has leading, trailing or doubled spaces")
    for pattern in (_BETWEEN, _SPAN):
        m = pattern.fullmatch(text)
        if m:
            a_cur, b_cur = m["a_cur"], m["b_cur"] or m["a_cur"]
            a_mul = m["a_mul"] or m["b_mul"]
            currencies = _currencies(a_cur)
            if _currencies(b_cur) != currencies:
                raise MoneyError("the two ends of the range use different currencies")
            low, high = _amount(m["a_num"], a_mul), _amount(m["b_num"], m["b_mul"])
            if not low < high:
                raise MoneyError("a range must run from a lower to a higher amount")
            qualifier = _QUALIFIERS[m["qual"].lower()] if m["qual"] else "exact"
            if qualifier in ("at_least", "up_to"):
                raise MoneyError(f"a range cannot also be qualified as {qualifier}")
            return Money(qualifier, currencies, low, high)
    m = _POINT.fullmatch(text)
    if not m:
        raise MoneyError(f"cannot read {text!r} as an amount; see the grammar in money.py")
    value = _amount(m["a_num"], m["a_mul"])
    qualifier = _QUALIFIERS[m["qual"].lower()] if m["qual"] else "exact"
    return Money(qualifier, _currencies(m["a_cur"]), value, value)
