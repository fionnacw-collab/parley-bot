"""
schedule.py — Curated Top League Fixture Schedule with 1-Click Deep Analysis Triggers.
Covers Premier League, La Liga, Serie A, Bundesliga, and UEFA Champions League.
"""

from __future__ import annotations

from datetime import datetime
from models import Leg, MarketCategory


def get_marquee_schedule() -> dict[str, list[dict]]:
    """
    Return curated top league matches grouped by competition with 1-click analysis data.
    """
    return {
        "Premier League 🏴󠁧󠁢󠁥󠁮󠁧󠁿": [
            {
                "id": "pl_1",
                "home": "Arsenal",
                "away": "Chelsea",
                "time": "Hari Ini, 23:30 WIB",
                "default_pick": "Over 2.5",
                "odds": 1.85,
                "market": MarketCategory.OVER_UNDER,
                "hot_badge": "🔥 Super Big Match",
            },
            {
                "id": "pl_2",
                "home": "Manchester City",
                "away": "Crystal Palace",
                "time": "Hari Ini, 21:00 WIB",
                "default_pick": "Man City -1.5",
                "odds": 1.75,
                "market": MarketCategory.HANDICAP,
                "hot_badge": "⭐ Banker Pick",
            },
            {
                "id": "pl_3",
                "home": "Liverpool",
                "away": "Tottenham",
                "time": "Besok, 22:30 WIB",
                "default_pick": "Both Teams to Score",
                "odds": 1.58,
                "market": MarketCategory.BTTS,
                "hot_badge": "⚽ High xG Match",
            },
        ],
        "La Liga 🇪🇸": [
            {
                "id": "ll_1",
                "home": "Real Madrid",
                "away": "Barcelona",
                "time": "Malam Ini, 02:00 WIB",
                "default_pick": "Real Madrid",
                "odds": 2.10,
                "market": MarketCategory.MATCH_WINNER,
                "hot_badge": "🔥 El Clásico (+EV)",
            },
            {
                "id": "ll_2",
                "home": "Atletico Madrid",
                "away": "Sevilla",
                "time": "Besok, 00:30 WIB",
                "default_pick": "Atletico Win",
                "odds": 1.65,
                "market": MarketCategory.MATCH_WINNER,
                "hot_badge": "🛡️ Strong Defense",
            },
        ],
        "Serie A 🇮🇹": [
            {
                "id": "sa_1",
                "home": "Inter Milan",
                "away": "Juventus",
                "time": "Dini Hari, 01:45 WIB",
                "default_pick": "Under 2.5",
                "odds": 1.78,
                "market": MarketCategory.OVER_UNDER,
                "hot_badge": "🔒 Derby d'Italia",
            },
            {
                "id": "sa_2",
                "home": "AC Milan",
                "away": "Napoli",
                "time": "Besok, 01:45 WIB",
                "default_pick": "Both Teams to Score",
                "odds": 1.70,
                "market": MarketCategory.BTTS,
                "hot_badge": "⚔️ Tactical Clash",
            },
        ],
        "Bundesliga 🇩🇪": [
            {
                "id": "bl_1",
                "home": "Bayern Munich",
                "away": "Borussia Dortmund",
                "time": "Besok, 23:30 WIB",
                "default_pick": "Over 3.5",
                "odds": 1.95,
                "market": MarketCategory.OVER_UNDER,
                "hot_badge": "🔥 Der Klassiker",
            },
            {
                "id": "bl_2",
                "home": "Bayer Leverkusen",
                "away": "RB Leipzig",
                "time": "Besok, 20:30 WIB",
                "default_pick": "Leverkusen Win",
                "odds": 1.90,
                "market": MarketCategory.MATCH_WINNER,
                "hot_badge": "💎 Value Edge",
            },
        ],
        "UEFA Champions League 🏆": [
            {
                "id": "ucl_1",
                "home": "Paris Saint-Germain",
                "away": "Manchester City",
                "time": "Kamis, 02:00 WIB",
                "default_pick": "Both Teams to Score",
                "odds": 1.62,
                "market": MarketCategory.BTTS,
                "hot_badge": "👑 European Elite",
            },
            {
                "id": "ucl_2",
                "home": "Real Madrid",
                "away": "Bayern Munich",
                "time": "Jumat, 02:00 WIB",
                "default_pick": "Over 2.5",
                "odds": 1.72,
                "market": MarketCategory.OVER_UNDER,
                "hot_badge": "⚡ Blockbuster UCL",
            },
        ],
    }


def get_schedule_match_by_id(match_id: str) -> dict | None:
    """Find a scheduled match by its ID."""
    all_leagues = get_marquee_schedule()
    for league, matches in all_leagues.items():
        for m in matches:
            if m["id"] == match_id:
                return m
    return None


def convert_schedule_match_to_leg(m: dict) -> Leg:
    """Convert schedule item into a Leg object for instant analysis."""
    return Leg(
        home=m["home"],
        away=m["away"],
        pick=m["default_pick"],
        odds=float(m["odds"]),
        market=m["market"],
        raw=f"{m['home']} vs {m['away']} - {m['default_pick']} @{m['odds']}",
    )
