"""
parser.py — Robust text and natural language parser for parlay tickets and match queries.
Includes native support for SBOBET Indonesian Odds (-1.15, 1.05) and Asian Handicap lines (0-0.5, 2.5-3).
"""

from __future__ import annotations

import re
from models import Leg, MarketCategory


def convert_sbobet_odds_to_decimal(raw_val: str | float | int) -> float:
    """
    Convert SBOBET Indonesian Odds (e.g. -1.15, -115, 1.05, 105) or Decimal Odds to standard European Decimal Odds.
    Formula:
    - Minus Odds (e.g. -1.15): Decimal = 1.0 + (1.0 / abs(odds)) = 1.87
    - Plus Odds (e.g. +1.05): Decimal = 1.0 + odds = 2.05
    - Standard Decimal (e.g. 1.85): Kept as 1.85
    """
    try:
        val_str = str(raw_val).strip().replace("@", "")
        # Remove parentheses if any: (-1.15) -> -1.15
        val_str = val_str.replace("(", "").replace(")", "").strip()

        # Handle 3-digit Indonesian format: -115 -> -1.15, 105 -> 1.05
        if re.match(r"^-[1-9]\d{2}$", val_str):
            val = float(val_str) / 100.0
        elif re.match(r"^\+?[1-9]\d{2}$", val_str) and not val_str.startswith("1."):
            val = float(val_str) / 100.0
        else:
            val = float(val_str)

        if val < 0:
            # Negative Indonesian Odds (Kena Kei / Pajak)
            dec = 1.0 + (1.0 / abs(val))
            return round(dec, 2)
        elif 0 < val < 1.05 and "+" in str(raw_val):
            # Positive Indonesian Odds with explicit plus (Dapat Kei)
            dec = 1.0 + val
            return round(dec, 2)
        elif val >= 1.01:
            # Already decimal odds
            return round(val, 2)
        else:
            return 1.85
    except Exception:
        return 1.85


def normalize_sbobet_handicap_line(pick: str) -> str:
    """
    Normalize SBOBET split lines into standard decimal notation:
    - 0-0.5 -> 0.25 (Voor 1/4)
    - 0.5-1 -> 0.75 (Voor 3/4)
    - 1-1.5 -> 1.25 (Voor 1 1/4)
    - 1.5-2 -> 1.75 (Voor 1 3/4)
    - 2-2.5 -> 2.25 (O/U 2 1/4)
    - 2.5-3 -> 2.75 (O/U 2 3/4)
    - 3-3.5 -> 3.25 (O/U 3 1/4)
    """
    replacements = [
        (r"\b0-0\.5\b", "0.25"),
        (r"\b0\.5-1\b", "0.75"),
        (r"\b1-1\.5\b", "1.25"),
        (r"\b1\.5-2\b", "1.75"),
        (r"\b2-2\.5\b", "2.25"),
        (r"\b2\.5-3\b", "2.75"),
        (r"\b3-3\.5\b", "3.25"),
    ]
    res = pick
    for pat, rep in replacements:
        res = re.sub(pat, rep, res)
    return res


# Pattern 1: Standard ticket format: "Arsenal vs Chelsea - Over 2.5 @1.85" or "@-1.15"
_STANDARD_RE = re.compile(
    r"^\s*"
    r"(?P<home>[^-\n\r]+?)"
    r"\s+(?:vs?\.?|v|-)\s+"
    r"(?P<away>[^-\n\r]+?)"
    r"\s*[-–—:]\s*"
    r"(?P<pick>[^@\n\r]+?)"
    r"(?:\s*[@:]\s*(?P<odds>[-+]?\d+(?:\.\d+)?|\([-+]?\d+(?:\.\d+)?\)))?"
    r"\s*$",
    re.IGNORECASE,
)

# Pattern 2: Natural query: "Arsenal vs Chelsea Over 2.5 @1.85" or "Milan vs Inter -1.15"
_INLINE_RE = re.compile(
    r"^\s*"
    r"(?P<home>[a-zA-Z0-9\s.]+?)"
    r"\s+(?:vs?\.?|v)\s+"
    r"(?P<away>[a-zA-Z0-9\s.]+?)"
    r"\s+(?P<pick>(?:Over|Under|O/U|BTTS|GG|NG|Home|Away|Draw|Win|HDP|\+|-|\d).*?)"
    r"(?:\s*[@:]\s*|\s+)(?P<odds>[-+]?\d+(?:\.\d+)?|\([-+]?\d+(?:\.\d+)?\))"
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
    Parse multi-line or single-line text into a list of structured Leg objects,
    supporting standard European odds and SBOBET Indonesian odds.
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
            raw_odds = m1.group("odds") or "1.90"
            odds_val = convert_sbobet_odds_to_decimal(raw_odds)
            clean_pick = normalize_sbobet_handicap_line(m1.group("pick").strip())
            leg = Leg(
                home=m1.group("home").strip(),
                away=m1.group("away").strip(),
                pick=clean_pick,
                odds=odds_val,
                raw=line_clean,
            )
            leg.market = leg.infer_market()
            legs.append(leg)
            continue

        # Try inline pattern
        m2 = _INLINE_RE.match(line_clean)
        if m2:
            raw_odds = m2.group("odds") or "1.90"
            odds_val = convert_sbobet_odds_to_decimal(raw_odds)
            clean_pick = normalize_sbobet_handicap_line(m2.group("pick").strip())
            leg = Leg(
                home=m2.group("home").strip(),
                away=m2.group("away").strip(),
                pick=clean_pick,
                odds=odds_val,
                raw=line_clean,
            )
            leg.market = leg.infer_market()
            legs.append(leg)
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
