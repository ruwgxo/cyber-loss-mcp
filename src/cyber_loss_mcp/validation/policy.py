"""Source policy constants (docs/DESIGN.md, section 4.3).

Every host here is an exact match. Adding one is a reviewed change to this file, never a
field in a record, so a record cannot vouch for its own source.
"""

from __future__ import annotations

SOURCE_HOSTS: dict[str, frozenset[str]] = {
    "sec_filing": frozenset({"www.sec.gov"}),
    "regulator_enforcement": frozenset(
        {
            "www.sec.gov",  # US SEC
            "www.ftc.gov",  # US FTC
            "www.hhs.gov",  # US HHS Office for Civil Rights
            "ico.org.uk",  # UK Information Commissioner's Office
            "www.edpb.europa.eu",  # European Data Protection Board
            "www.dataprotection.ie",  # Ireland, Data Protection Commission
            "www.dfs.ny.gov",  # New York State Department of Financial Services
            # US state attorneys general are added one domain at a time, when needed.
        }
    ),
    # Official court and settlement-administrator domains, added one at a time.
    "court_record": frozenset(),
}

# A company statement is accepted only from that company's own domain, listed here
# against the incident id that cites it.
COMPANY_HOSTS: dict[str, frozenset[str]] = {}

# ISO 4217 codes accepted so far. A code missing here fails validation; add it when a
# source needs it.
CURRENCIES = frozenset(
    {
        "AED", "AUD", "BRL", "CAD", "CHF", "CNY", "DKK", "EUR", "GBP", "HKD", "ILS",
        "INR", "JPY", "KRW", "MXN", "NOK", "NZD", "PLN", "SEK", "SGD", "USD", "ZAR",
    }
)  # fmt: skip

# What each currency symbol can mean. "$" alone is ambiguous, so the record's
# ``currency`` field picks one of these and the validator checks it is allowed.
CURRENCY_SYMBOLS: dict[str, frozenset[str]] = {
    "$": frozenset({"USD", "CAD", "AUD", "NZD", "SGD", "HKD"}),
    "US$": frozenset({"USD"}),
    "C$": frozenset({"CAD"}),
    "A$": frozenset({"AUD"}),
    "NZ$": frozenset({"NZD"}),
    "S$": frozenset({"SGD"}),
    "HK$": frozenset({"HKD"}),
    "£": frozenset({"GBP"}),
    "€": frozenset({"EUR"}),
    "¥": frozenset({"JPY", "CNY"}),
}

# Quote length cap, matching the domain schema.
MAX_QUOTE_CHARS = 300
