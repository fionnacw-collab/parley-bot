"""
football_api.py — RapidAPI API-Football v3 client with in-memory caching and fallback.
Fetches team form, head-to-head records, goal statistics, and league context.
"""

from __future__ import annotations

import logging
import time
from typing import Any
import httpx

from config import settings
from models import H2HStats, TeamStats

logger = logging.getLogger(__name__)

API_URL = "https://api-football-v1.p.rapidapi.com/v3"

# In-memory cache: key -> (timestamp, data)
_CACHE: dict[str, tuple[float, Any]] = {}
CACHE_TTL = 3600  # 1 hour


def _get_cache(key: str) -> Any | None:
    if key in _CACHE:
        ts, data = _CACHE[key]
        if time.time() - ts < CACHE_TTL:
            return data
        del _CACHE[key]
    return None


def _set_cache(key: str, data: Any):
    _CACHE[key] = (time.time(), data)


def _headers() -> dict[str, str]:
    return {
        "X-RapidAPI-Key": settings.rapidapi_key,
        "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com",
    }


async def search_team(client: httpx.AsyncClient, name: str) -> dict | None:
    """Search for team ID and basic details."""
    cache_key = f"team_search:{name.lower().strip()}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    if not settings.has_rapidapi:
        return None

    try:
        resp = await client.get(
            f"{API_URL}/teams",
            headers=_headers(),
            params={"search": name},
            timeout=8.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            response = data.get("response", [])
            if response:
                team_info = response[0]["team"]
                _set_cache(cache_key, team_info)
                return team_info
    except Exception as e:
        logger.warning(f"Error searching team '{name}': {e}")

    return None


async def get_team_fixtures(client: httpx.AsyncClient, team_id: int, last: int = 8) -> list[dict]:
    """Get last N completed matches for a team."""
    cache_key = f"fixtures:{team_id}:{last}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    if not settings.has_rapidapi:
        return []

    try:
        resp = await client.get(
            f"{API_URL}/fixtures",
            headers=_headers(),
            params={"team": team_id, "last": last, "status": "FT"},
            timeout=8.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            fixtures = data.get("response", [])
            _set_cache(cache_key, fixtures)
            return fixtures
    except Exception as e:
        logger.warning(f"Error getting fixtures for team {team_id}: {e}")

    return []


async def get_h2h(client: httpx.AsyncClient, team1_id: int, team2_id: int, last: int = 8) -> H2HStats:
    """Fetch head-to-head records between two teams."""
    cache_key = f"h2h:{min(team1_id, team2_id)}:{max(team1_id, team2_id)}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    default_h2h = H2HStats()

    if not settings.has_rapidapi:
        return default_h2h

    try:
        resp = await client.get(
            f"{API_URL}/fixtures/headtohead",
            headers=_headers(),
            params={"h2h": f"{team1_id}-{team2_id}", "last": last},
            timeout=8.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            fixtures = data.get("response", [])
            if not fixtures:
                return default_h2h

            t1_wins = 0
            t2_wins = 0
            draws = 0
            total_goals = 0
            btts_count = 0
            over_25_count = 0
            recent_scores = []

            for f in fixtures:
                home_goals = f["goals"]["home"] or 0
                away_goals = f["goals"]["away"] or 0
                h_id = f["teams"]["home"]["id"]

                total_goals += home_goals + away_goals
                if (home_goals + away_goals) > 2.5:
                    over_25_count += 1
                if home_goals > 0 and away_goals > 0:
                    btts_count += 1

                score_str = f"{f['teams']['home']['name']} {home_goals}-{away_goals} {f['teams']['away']['name']}"
                recent_scores.append(score_str)

                if home_goals == away_goals:
                    draws += 1
                elif (h_id == team1_id and home_goals > away_goals) or (h_id != team1_id and away_goals > home_goals):
                    t1_wins += 1
                else:
                    t2_wins += 1

                if len(recent_scores) >= 5:
                    break

            n = len(fixtures)
            h2h_result = H2HStats(
                total_matches=n,
                home_wins=t1_wins,
                draws=draws,
                away_wins=t2_wins,
                btts_pct=round(btts_count / n, 2) if n else 0.50,
                over_25_pct=round(over_25_count / n, 2) if n else 0.50,
                avg_goals=round(total_goals / n, 2) if n else 2.50,
                recent_scores=recent_scores,
            )
            _set_cache(cache_key, h2h_result)
            return h2h_result
    except Exception as e:
        logger.warning(f"Error fetching H2H {team1_id} vs {team2_id}: {e}")

    return default_h2h


def _build_team_stats_from_fixtures(name: str, team_id: int, fixtures: list[dict], is_home: bool) -> TeamStats:
    """Derive comprehensive statistical metrics from match fixtures."""
    if not fixtures:
        return TeamStats(
            name=name,
            team_id=team_id,
            form_str="D-W-L-W-D",
            wins=2,
            draws=2,
            losses=1,
            goals_scored_avg=1.45 if is_home else 1.20,
            goals_conceded_avg=1.10 if is_home else 1.30,
            clean_sheet_pct=0.30 if is_home else 0.20,
            failed_to_score_pct=0.15 if is_home else 0.25,
        )

    wins = 0
    draws = 0
    losses = 0
    goals_scored = 0
    goals_conceded = 0
    clean_sheets = 0
    failed_to_score = 0
    form_chars = []

    for f in fixtures:
        goals = f.get("goals", {})
        h_g = goals.get("home") if goals.get("home") is not None else 0
        a_g = goals.get("away") if goals.get("away") is not None else 0
        h_id = f.get("teams", {}).get("home", {}).get("id")

        if h_id == team_id:
            scored, conceded = h_g, a_g
        else:
            scored, conceded = a_g, h_g

        goals_scored += scored
        goals_conceded += conceded

        if scored == 0:
            failed_to_score += 1
        if conceded == 0:
            clean_sheets += 1

        if scored > conceded:
            wins += 1
            form_chars.append("W")
        elif scored == conceded:
            draws += 1
            form_chars.append("D")
        else:
            losses += 1
            form_chars.append("L")

    n = len(fixtures)
    return TeamStats(
        name=name,
        team_id=team_id,
        form_str="-".join(form_chars[:5]) if form_chars else "N/A",
        wins=wins,
        draws=draws,
        losses=losses,
        goals_scored_avg=round(goals_scored / n, 2) if n else 1.35,
        goals_conceded_avg=round(goals_conceded / n, 2) if n else 1.25,
        clean_sheet_pct=round(clean_sheets / n, 2) if n else 0.25,
        failed_to_score_pct=round(failed_to_score / n, 2) if n else 0.20,
    )


async def fetch_full_match_context(home_name: str, away_name: str) -> tuple[TeamStats, TeamStats, H2HStats]:
    """Fetch home team stats, away team stats, and head-to-head records."""
    async with httpx.AsyncClient() as client:
        home_team = await search_team(client, home_name)
        away_team = await search_team(client, away_name)

        home_id = home_team["id"] if home_team else 0
        away_id = away_team["id"] if away_team else 0

        home_fixtures = await get_team_fixtures(client, home_id) if home_id else []
        away_fixtures = await get_team_fixtures(client, away_id) if away_id else []

        h2h = await get_h2h(client, home_id, away_id) if home_id and away_id else H2HStats()

        home_stats = _build_team_stats_from_fixtures(home_name, home_id, home_fixtures, is_home=True)
        away_stats = _build_team_stats_from_fixtures(away_name, away_id, away_fixtures, is_home=False)

        return home_stats, away_stats, h2h
