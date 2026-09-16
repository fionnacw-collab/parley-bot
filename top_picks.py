"""
top_picks.py — Real-Time Factual AI Top Betting Selections from soccervital.com & Quant Model.
Categorizes selections into Safe Anchors, High +EV Value Bets, and Goals/Over-Under.
"""

from __future__ import annotations

from models import Leg, MarketCategory, TopPickItem
import soccervital


async def get_daily_top_picks() -> list[TopPickItem]:
    """Fetch real-time daily Top Betting Picks from SoccerVital live feed."""
    return await soccervital.fetch_soccervital_bets_of_the_day()


async def get_top_pick_by_id(pick_id: str) -> TopPickItem | None:
    """Find a specific top pick item by ID from real-time live picks."""
    picks = await get_daily_top_picks()
    for p in picks:
        if p.id == pick_id:
            return p
    return None


def convert_top_pick_to_leg(pick: TopPickItem) -> Leg:
    """Convert a TopPickItem to a Leg object for instant analysis."""
    parts = pick.match_title.split(" vs ")
    home = parts[0].strip() if len(parts) > 0 else "Home Team"
    away = parts[1].strip() if len(parts) > 1 else "Away Team"
    return Leg(
        home=home,
        away=away,
        pick=pick.pick,
        odds=pick.odds,
        market=pick.market,
        raw=f"{home} vs {away} - {pick.pick} @{pick.odds}",
    )
