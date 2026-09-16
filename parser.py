"""
parser.py — Robust text and natural language parser for parlay tickets and match queries.
Supports multiple input conventions, delimiters, and conversational formats.
"""

from __future__ import annotations

import re
from models import Leg, MarketCategory

# Pattern 1: Standard ticket format: "Arsenal vs Chelsea - Over 2.5 @1.85"
_STANDARD_RE = re.compile(
    r"^\s*"
    r"(?P<home>[^-\n\r]+?)"
    r"\s+(?:vs?\.?|v|-)\s+"
    r"(?P<away>[^-\n\r]+?)"
    r"\s*[-–—:]\s*"
    r"(?P<pick>[^@\n\r]+?)"
    r"(?:\s*[@:]\s*(?P<odds>\d+(?:\.\d+)?))?"
    r"\s*$",
    re.IGNORECASE,
)

# Pattern 2: Natural query: "Arsenal vs Chelsea Over 2.5 @1.85" or "Milan vs Inter ML 2.10"
_INLINE_RE = re.compile(
    r"^\s*"
    r"(?P<home>[a-zA-Z0-9\s.]+?)"
    r"\s+(?:vs?\.?|v)\s+"
    r"(?P<away>[a-zA-Z0-9\s.]+?)"
    r"\s+(?P<pick>(?:Over|Under|O/U|BTTS|GG|NG|Home|Away|Draw|Win|HDP|\+|-|\d).*?)"
    r"(?:\s*[@:]\s*|\s+)(?P<odds>\d+(?:\.\d+)?)"
    r"\s*$",
    re.IGNORECASE,
)

# Pattern 3: Simple match query: "Arsenal vs Chelsea" (defaults to standard 1X2 market)
_SIMPLE_MATCH_RE = re.compile(
    r"^\s*(?:/analyze\s+)?(?P<home>[a-zA-Z0-9\s.]+?)\s+(?:vs?\.?|v)\s+(?P<away>[a-zA-Z0-9\s.]+?)\s*$",
    re.IGNORECASE,
)


def parse_legs(text: str) -> list[Leg]:
    """
    Parse multi-line or single-line text into a list of structured Leg objects.
    """
    legs: list[Leg] = []
    lines = text.strip().splitlines()

    for line in lines:
        line_clean = line.strip()
        if not line_clean or line_clean.startswith("#"):
            continue

        # Strip leading numbers/bullets (e.g., "1.", "1)", "[1]", "-", "•", "*")
        line_clean = re.sub(r"^(?:\[?\d+[.)\]]|\*|-|•)\s*", "", line_clean).strip()
        if not line_clean:
            continue
        # Try standard pattern
        m1 = _STANDARD_RE.match(line_clean)
        if m1:
            odds_val = float(m1.group("odds")) if m1.group("odds") else 1.90
            legs.append(
                Leg(
                    home=m1.group("home").strip(),
                    away=m1.group("away").strip(),
                    pick=m1.group("pick").strip(),
                    odds=odds_val,
                    raw=line_clean,
                )
            )
            continue

        # Try inline pattern
        m2 = _INLINE_RE.match(line_clean)
        if m2:
            odds_val = float(m2.group("odds")) if m2.group("odds") else 1.90
            legs.append(
                Leg(
                    home=m2.group("home").strip(),
                    away=m2.group("away").strip(),
                    pick=m2.group("pick").strip(),
                    odds=odds_val,
                    raw=line_clean,
                )
            )
            continue

        # Try simple match pattern (e.g. /analyze Arsenal vs Chelsea)
        m3 = _SIMPLE_MATCH_RE.match(line_clean)
        if m3:
            legs.append(
                Leg(
                    home=m3.group("home").strip(),
                    away=m3.group("away").strip(),
                    pick="Home Win",
                    odds=1.90,
                    market=MarketCategory.MATCH_WINNER,
                    raw=line_clean,
                )
            )

    return legs
