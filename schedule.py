"""
schedule.py — Real-Time Live Fixture Schedule from soccervital.com with 1-Click Deep Analysis Triggers.
Groups live matches by League for TODAY and TOMORROW.
"""

from __future__ import annotations

from models import Leg, MarketCategory
import soccervital


async def get_realtime_schedule(day: str = "today") -> dict[str, list[dict]]:
    """
    Return real-time live matches grouped by competition for TODAY or TOMORROW.
    """
    if day.lower() == "tomorrow":
        raw_matches = await soccervital.fetch_soccervital_tomorrow()
    else:
        raw_matches = await soccervital.fetch_soccervital_today()

    grouped: dict[str, list[dict]] = {}
    for m in raw_matches:
        league = m.get("league", "Other Competitions")
        if league not in grouped:
            grouped[league] = []

        # Default recommended pick based on SoccerVital tip
        tip = m.get("tip", "1").upper()
        home = m["home"]
        away = m["away"]
        odd1 = float(m.get("odds_1", 1.85))
        odd2 = float(m.get("odds_2", 2.10))

        if tip == "1":
            default_pick = f"{home} Win"
            odds_val = odd1
            market = MarketCategory.MATCH_WINNER
        elif tip == "2":
            default_pick = f"{away} Win"
            odds_val = odd2
            market = MarketCategory.MATCH_WINNER
        elif tip in ("1X", "X2"):
            team = home if "1" in tip else away
            default_pick = f"{team} or Draw"
            odds_val = 1.45
            market = MarketCategory.DOUBLE_CHANCE
        else:
            default_pick = "Over 2.5 Goals" if m.get("goals") == "O" else f"{home} Win"
            odds_val = 1.80
            market = MarketCategory.OVER_UNDER

        m_enriched = dict(m)
        m_enriched["default_pick"] = default_pick
        m_enriched["odds"] = odds_val
        m_enriched["market"] = market

        score_pred = m.get("score", "")
        m_enriched["hot_badge"] = f"🎯 Prediksi Skor: {score_pred}" if score_pred else "⚽ Live Match"

        grouped[league].append(m_enriched)

    return grouped


async def get_schedule_match_by_id(match_id: str) -> dict | None:
    """Find a scheduled match by its ID from live data."""
    today_dict = await get_realtime_schedule("today")
    for matches in today_dict.values():
        for m in matches:
            if m["id"] == match_id:
                return m

    tom_dict = await get_realtime_schedule("tomorrow")
    for matches in tom_dict.values():
        for m in matches:
            if m["id"] == match_id:
                return m

    return None


def convert_schedule_match_to_leg(m: dict) -> Leg:
    """Convert schedule item into a Leg object for instant analysis."""
    return Leg(
        home=m["home"],
        away=m["away"],
        pick=m.get("default_pick", f"{m['home']} Win"),
        odds=float(m.get("odds", 1.85)),
        market=m.get("market", MarketCategory.MATCH_WINNER),
        raw=f"{m['home']} vs {m['away']} - {m.get('default_pick', 'Win')} @{m.get('odds', 1.85)}",
    )
