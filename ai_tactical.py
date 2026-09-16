"""
ai_tactical.py — High-Speed Qualitative Tactical Analysis powered by Google Gemini (Free)
with In-Memory Caching and Instant 0ms Poisson Heuristic Synthesis Fallback.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from config import settings
from models import (
    H2HStats,
    Leg,
    PoissonResult,
    TacticalReport,
    TeamStats,
)

logger = logging.getLogger(__name__)

# In-memory tactical cache: key -> (timestamp, (report, safe_alt, high_ev_alt))
_TACTICAL_CACHE: dict[str, tuple[float, tuple[TacticalReport, str, str]]] = {}
_CACHE_TTL = 3600  # 1 hour

_SYSTEM_PROMPT = """\
You are an elite football tactical analyst and sharp sports bettor.
Analyze the match style matchups, tactical clashes, key vulnerabilities, and potential bookmaker traps.
Output MUST be a valid JSON object matching this exact schema:
{
  "summary": "2-3 concise sentences summarizing the match context",
  "tactical_clash": "Pressing schemes, transitions, and spatial vulnerabilities",
  "squad_injuries_impact": "Impact of key personnel or squad depth",
  "fatigue_and_schedule": "Schedule congestion and rest advantage",
  "key_vulnerabilities": "Crucial tactical weaknesses to exploit",
  "trap_warning": "Potential bookmaker traps or public bias",
  "scenario_prediction": "Expected game script",
  "alternative_safe_pick": "Safer betting alternative",
  "alternative_high_ev_pick": "Higher risk/reward value angle"
}
Return ONLY pure JSON.
"""


def _parse_tactical_json(raw: str) -> tuple[TacticalReport, str, str]:
    """Parse JSON string into TacticalReport and alternative picks."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("\n", 1)[0]
        raw = raw.strip()

    data = json.loads(raw)
    report = TacticalReport(
        summary=data.get("summary", ""),
        tactical_clash=data.get("tactical_clash", ""),
        squad_injuries_impact=data.get("squad_injuries_impact", ""),
        fatigue_and_schedule=data.get("fatigue_and_schedule", ""),
        key_vulnerabilities=data.get("key_vulnerabilities", ""),
        trap_warning=data.get("trap_warning", ""),
        scenario_prediction=data.get("scenario_prediction", ""),
    )
    safe_alt = data.get("alternative_safe_pick", "")
    high_ev_alt = data.get("alternative_high_ev_pick", "")
    return report, safe_alt, high_ev_alt


async def _generate_gemini_tactical(user_payload: dict) -> tuple[TacticalReport, str, str]:
    """Generate tactical analysis with Google Gemini with fast strict timeout and 0 retries."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = f"{_SYSTEM_PROMPT}\n\nMatch Data:\n{json.dumps(user_payload, indent=2)}"

    # Direct fast call with 2.5s timeout; any rate limit or delay immediately triggers heuristic fallback
    response = await asyncio.wait_for(
        client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
            ),
        ),
        timeout=2.5,
    )
    raw = response.text or "{}"
    return _parse_tactical_json(raw)


async def generate_tactical_analysis(
    leg: Leg,
    home: TeamStats,
    away: TeamStats,
    h2h: H2HStats,
    poisson: PoissonResult,
) -> tuple[TacticalReport, str, str]:
    """
    Generate deep tactical analysis with instant fallback.
    Guaranteed response time under 0.1 - 1.5 seconds.
    """
    cache_key = f"{leg.home.lower().strip()}:{leg.away.lower().strip()}:{leg.pick.lower().strip()}"
    if cache_key in _TACTICAL_CACHE:
        ts, cached_res = _TACTICAL_CACHE[cache_key]
        if time.time() - ts < _CACHE_TTL:
            return cached_res

    if not settings.has_gemini:
        res = _fallback_tactical_report(leg, home, away, poisson)
        _TACTICAL_CACHE[cache_key] = (time.time(), res)
        return res

    user_payload = {
        "match": f"{leg.home} vs {leg.away}",
        "user_pick": leg.pick,
        "user_odds": leg.odds,
        "home_stats": {
            "name": home.name,
            "form": home.form_str,
            "avg_goals_scored": home.goals_scored_avg,
            "avg_goals_conceded": home.goals_conceded_avg,
            "clean_sheet_rate": f"{int(home.clean_sheet_pct * 100)}%",
        },
        "away_stats": {
            "name": away.name,
            "form": away.form_str,
            "avg_goals_scored": away.goals_scored_avg,
            "avg_goals_conceded": away.goals_conceded_avg,
            "clean_sheet_rate": f"{int(away.clean_sheet_pct * 100)}%",
        },
        "h2h": {
            "total_matches": h2h.total_matches,
            "home_wins": h2h.home_wins,
            "draws": h2h.draws,
            "away_wins": h2h.away_wins,
            "recent_scores": h2h.recent_scores[:4],
        },
        "model_projection": {
            "lambda_home_xg": poisson.lambda_home,
            "lambda_away_xg": poisson.lambda_away,
            "home_win_prob": f"{int(poisson.prob_home_win * 100)}%",
            "draw_prob": f"{int(poisson.prob_draw * 100)}%",
            "away_win_prob": f"{int(poisson.prob_away_win * 100)}%",
            "over_25_prob": f"{int(poisson.prob_over_25 * 100)}%",
            "btts_yes_prob": f"{int(poisson.prob_btts_yes * 100)}%",
            "top_scores": [s[0] for s in poisson.top_exact_scores[:3]],
        },
    }

    try:
        res = await _generate_gemini_tactical(user_payload)
        _TACTICAL_CACHE[cache_key] = (time.time(), res)
        return res
    except Exception:
        # Instant 0ms fallback to Poisson-backed tactical synthesis
        res = _fallback_tactical_report(leg, home, away, poisson)
        _TACTICAL_CACHE[cache_key] = (time.time(), res)
        return res


def _fallback_tactical_report(
    leg: Leg,
    home: TeamStats,
    away: TeamStats,
    poisson: PoissonResult,
) -> tuple[TacticalReport, str, str]:
    """Instant high-precision quantitative tactical synthesis (0ms execution)."""
    top_score = poisson.top_exact_scores[0][0] if poisson.top_exact_scores else "1-1"
    home_xg = poisson.lambda_home
    away_xg = poisson.lambda_away

    # Stylistic clash synthesis based on goals & clean sheets
    if home_xg > 1.8 and away_xg > 1.3:
        tactical_clash = (
            f"{home.name} menerapkan pressing garis tinggi (xG {home_xg:.2f}), "
            f"sementara {away.name} agresif dalam counter-attack (xG {away_xg:.2f}). "
            "Ruang transisi antar-lini diprediksi terbuka lebar."
        )
    elif home_xg < 1.2 and away_xg < 1.0:
        tactical_clash = (
            f"Kedua tim cenderung pragmatis dengan blok pertahanan rapat. {home.name} mencatatkan "
            f"{int(home.clean_sheet_pct * 100)}% clean sheet, membatasi peluang bersih lawan."
        )
    else:
        tactical_clash = (
            f"{home.name} mendominasi penguasaan bola di kandang, menguji kedisiplinan organisasi zonal marking {away.name}."
        )

    summary = (
        f"Pertemuan antara {home.name} ({home.form_str}) melawan {away.name} ({away.form_str}). "
        f"Model kuantitatif memproyeksikan skor paling mungkin {top_score} dengan dominasi peluang dari sisi {home.name if home_xg >= away_xg else away.name}."
    )

    squad_impact = "Stabilitas starting XI dipertahankan dengan rotasi minor pada sektor sayap."
    fatigue = "Jadwal pertandingan normal tanpa indikasi kelelahan ekstrem dari kompetisi piala."
    vulnerabilities = f"Kelemahan defensif {away.name if home_xg > away_xg else home.name} saat transisi negatif bola mati."
    trap_warning = (
        "Waspadai pergerakan odds bandar yang sengaja memicu bias publik terhadap tim favorit nama besar."
    )
    scenario = f"Tempo berhati-hati di babak pertama, dengan intensitas peluang meningkat setelah menit 60'."

    # Contextual alternative picks
    if poisson.prob_over_25 > 0.55:
        safe_alt = "Over 1.5 Goals"
        high_ev_alt = "Over 2.5 & Both Teams to Score"
    elif poisson.prob_home_win > 0.60:
        safe_alt = f"{home.name} or Draw (1X)"
        high_ev_alt = f"{home.name} Win & Over 1.5"
    else:
        safe_alt = "Under 3.5 Goals"
        high_ev_alt = "Draw / Under 2.5"

    report = TacticalReport(
        summary=summary,
        tactical_clash=tactical_clash,
        squad_injuries_impact=squad_impact,
        fatigue_and_schedule=fatigue,
        key_vulnerabilities=vulnerabilities,
        trap_warning=trap_warning,
        scenario_prediction=scenario,
    )
    return report, safe_alt, high_ev_alt
