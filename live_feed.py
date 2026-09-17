"""
live_feed.py — Real-Time Live Match Fixtures, Top Picks, & Live Scores from soccervital.com.
Powers real-time match schedules, daily banker picks, and live match timeline monitoring.
"""

from __future__ import annotations

import logging
import time
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 600  # 10 minutes TTL


def _get_cache(key: str) -> list[dict] | None:
    if key in _CACHE:
        ts, data = _CACHE[key]
        if time.time() - ts < _CACHE_TTL:
            return data
    return None


def _set_cache(key: str, data: list[dict]):
    _CACHE[key] = (time.time(), data)


async def fetch_today_schedule() -> list[dict]:
    """Fetch today's real-time live matches from SoccerVital."""
    cached = _get_cache("today_schedule")
    if cached:
        return cached

    url = "https://www.soccervital.com/"
    matches: list[dict] = []

    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                tables = soup.find_all("table")

                for t in tables:
                    rows = t.find_all("tr")
                    current_league = "General League"
                    for row in rows:
                        tds = row.find_all("td")
                        if not tds:
                            continue

                        a_tag = row.find("a")
                        if len(tds) <= 3 and a_tag and "table-" in str(a_tag.get("href", "")):
                            current_league = a_tag.get_text(strip=True)
                            continue

                        if len(tds) >= 8:
                            time_str = tds[0].get_text(strip=True)
                            home = tds[1].get_text(strip=True)
                            away = tds[2].get_text(strip=True)
                            odd1 = tds[3].get_text(strip=True)
                            oddX = tds[4].get_text(strip=True)
                            odd2 = tds[5].get_text(strip=True)
                            tip = tds[6].get_text(strip=True)
                            goals = tds[7].get_text(strip=True)
                            score = tds[8].get_text(strip=True) if len(tds) > 8 else "2:1"

                            if home and away and odd1:
                                matches.append(
                                    {
                                        "id": f"live_today_{len(matches)+1}",
                                        "league": current_league,
                                        "time": f"Hari Ini, {time_str} WIB",
                                        "home": home,
                                        "away": away,
                                        "odds_1": _clean_float(odd1, 1.85),
                                        "odds_x": _clean_float(oddX, 3.20),
                                        "odds_2": _clean_float(odd2, 2.10),
                                        "tip": tip,
                                        "goals": goals,
                                        "pred_score": score or "2:1",
                                        "day": "TODAY",
                                    }
                                )

                if matches:
                    _set_cache("today_schedule", matches)
                    return matches
    except Exception as e:
        logger.warning(f"Error fetching today schedule: {e}")

    return _fallback_today_fixtures()


async def fetch_tomorrow_schedule() -> list[dict]:
    """Fetch tomorrow's real-time live matches from SoccerVital."""
    cached = _get_cache("tomorrow_schedule")
    if cached:
        return cached

    url = "https://www.soccervital.com/bet/?sh=1"
    matches: list[dict] = []

    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                tables = soup.find_all("table")

                for t in tables:
                    rows = t.find_all("tr")
                    current_league = "General League"
                    for row in rows:
                        tds = row.find_all("td")
                        if not tds:
                            continue

                        a_tag = row.find("a")
                        if len(tds) <= 3 and a_tag and "table-" in str(a_tag.get("href", "")):
                            current_league = a_tag.get_text(strip=True)
                            continue

                        if len(tds) >= 4:
                            time_str = tds[0].get_text(strip=True)
                            home = tds[1].get_text(strip=True)
                            away = tds[2].get_text(strip=True)
                            tip_str = tds[3].get_text(strip=True) if len(tds) > 3 else ""

                            odds_val = 1.80
                            if "(" in tip_str and ")" in tip_str:
                                try:
                                    odds_val = float(tip_str.split("(")[1].split(")")[0])
                                except Exception:
                                    pass

                            if home and away:
                                matches.append(
                                    {
                                        "id": f"live_tom_{len(matches)+1}",
                                        "league": current_league,
                                        "time": f"Besok, {time_str} WIB",
                                        "home": home,
                                        "away": away,
                                        "odds_1": odds_val,
                                        "odds_x": 3.40,
                                        "odds_2": odds_val,
                                        "tip": "1" if home in tip_str else "2",
                                        "pred_score": "2:1",
                                        "day": "TOMORROW",
                                    }
                                )

                if matches:
                    _set_cache("tomorrow_schedule", matches)
                    return matches
    except Exception as e:
        logger.warning(f"Error fetching tomorrow schedule: {e}")

    return _fallback_tomorrow_fixtures()


async def fetch_live_scores() -> dict[str, dict]:
    """
    Fetch real-time live match scores and statuses for slip monitoring.
    Returns mapping: 'home_clean vs away_clean' -> {'home_score': int, 'away_score': int, 'status': str, 'summary': str}
    """
    url = "https://www.soccervital.com/livescores/"
    live_scores: dict[str, dict] = {}

    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for tr in soup.find_all("tr"):
                    tds = tr.find_all("td")
                    if len(tds) >= 4:
                        status_str = tds[0].get_text(strip=True)
                        home = tds[1].get_text(strip=True)
                        score_raw = tds[2].get_text(strip=True)
                        away = tds[3].get_text(strip=True)

                        if home and away and ":" in score_raw:
                            try:
                                h_s, a_s = score_raw.split(":", 1)
                                key = f"{home.lower().strip()} vs {away.lower().strip()}"
                                live_scores[key] = {
                                    "home_score": int(h_s.strip()),
                                    "away_score": int(a_s.strip()),
                                    "status": status_str or "LIVE",
                                    "summary": f"{home} {score_raw} {away} ({status_str})",
                                }
                            except Exception:
                                pass
    except Exception as e:
        logger.debug(f"Error fetching live scores feed: {e}")

    return live_scores


def _clean_float(val: str, default: float) -> float:
    try:
        clean = val.replace(",", ".").strip()
        return float(clean)
    except Exception:
        return default


def _fallback_today_fixtures() -> list[dict]:
    return [
        {
            "id": "fb_1",
            "league": "UEFA Europa League",
            "time": "Hari Ini, 20:00 WIB",
            "home": "Bayer Leverkusen",
            "away": "NK Celje",
            "odds_1": 1.17,
            "odds_x": 7.50,
            "odds_2": 15.00,
            "tip": "1",
            "goals": "O",
            "pred_score": "4:1",
            "day": "TODAY",
        },
        {
            "id": "fb_2",
            "league": "Spain La Liga",
            "time": "Hari Ini, 20:30 WIB",
            "home": "Barcelona",
            "away": "Racing Santander",
            "odds_1": 1.06,
            "odds_x": 13.00,
            "odds_2": 23.00,
            "tip": "1",
            "goals": "O",
            "pred_score": "4:1",
            "day": "TODAY",
        },
        {
            "id": "fb_3",
            "league": "England EFL Cup",
            "time": "Hari Ini, 20:00 WIB",
            "home": "Man Utd",
            "away": "Brighton",
            "odds_1": 1.76,
            "odds_x": 3.80,
            "odds_2": 4.10,
            "tip": "1X",
            "goals": "O",
            "pred_score": "3:1",
            "day": "TODAY",
        },
        {
            "id": "fb_4",
            "league": "Spain La Liga",
            "time": "Hari Ini, 18:00 WIB",
            "home": "Atletico Madrid",
            "away": "Osasuna",
            "odds_1": 1.40,
            "odds_x": 4.50,
            "odds_2": 7.50,
            "tip": "1",
            "goals": "U",
            "pred_score": "2:0",
            "day": "TODAY",
        },
    ]


def _fallback_tomorrow_fixtures() -> list[dict]:
    return [
        {
            "id": "fbt_1",
            "league": "UEFA Europa League",
            "time": "Besok, 20:00 WIB",
            "home": "AC Milan",
            "away": "Benfica",
            "odds_1": 2.10,
            "odds_x": 3.50,
            "odds_2": 3.25,
            "tip": "1X",
            "pred_score": "3:1",
            "day": "TOMORROW",
        },
        {
            "id": "fbt_2",
            "league": "UEFA Europa League",
            "time": "Besok, 20:00 WIB",
            "home": "Anderlecht",
            "away": "Lyon",
            "odds_1": 3.50,
            "odds_x": 3.70,
            "odds_2": 1.95,
            "tip": "X2",
            "pred_score": "2:3",
            "day": "TOMORROW",
        },
    ]
