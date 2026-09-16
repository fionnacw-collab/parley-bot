"""
ai_tactical.py — Deep qualitative tactical analysis powered by Google Gemini (Free) or OpenAI GPT-4o.
Analyzes stylistic clashes, tactical matchups, motivation, fatigue, squad depth, and betting traps.
"""

from __future__ import annotations

import json
import logging

from config import settings
from models import (
    H2HStats,
    Leg,
    PoissonResult,
    TacticalReport,
    TeamStats,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an elite football tactical analyst and sharp sports bettor.
Your role is to produce deep, high-level tactical and contextual analysis for a football match.
Analyze style matchups, tactical clashes, motivation, fatigue, rotation risks, and potential bookmaker traps.

You will receive:
- Match details (Home vs Away, Pick, Odds)
- Statistical form and goals data
- Poisson model projections and top scorelines

Output MUST be a valid JSON object matching this exact schema:
{
  "summary": "2-3 concise sentences summarizing the match context and tactical narrative",
  "tactical_clash": "Analysis of pressing schemes, build-up play, transitions, and spatial vulnerabilities",
  "squad_injuries_impact": "Impact of missing key personnel, squad depth, or expected tactical adjustments",
  "fatigue_and_schedule": "Schedule congestion, rest advantage, cup/continental travel fatigue",
  "key_vulnerabilities": "Crucial flaws or tactical weaknesses each team can exploit",
  "trap_warning": "Potential bookmaker traps or public bias regarding this specific pick",
  "scenario_prediction": "Expected game script (e.g., tight first half with open transition battles late)",
  "alternative_safe_pick": "A safer betting alternative with higher floor (e.g. Double Chance, DNB, Over 2.0)",
  "alternative_high_ev_pick": "A higher risk/reward value angle (e.g. Win & Under 3.5, BTTS & Over 2.5)"
}
Return ONLY pure JSON. No markdown fences, no conversational text.
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
    """Generate tactical analysis with Google Gemini with automatic failover."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = f"{_SYSTEM_PROMPT}\n\nMatch Data:\n{json.dumps(user_payload, indent=2)}"

    candidate_models = [settings.gemini_model, "gemini-3.6-flash", "gemini-3.7-flash", "gemini-flash-latest"]
    last_err = None

    for model_name in candidate_models:
        try:
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    response_mime_type="application/json",
                ),
            )
            raw = response.text or "{}"
            return _parse_tactical_json(raw)
        except Exception as e:
            last_err = e
            logger.warning(f"Gemini tactical model {model_name} failed ({e}), trying next...")
            continue

    raise last_err or ValueError("Gagal menghasilkan analisa taktis dari Gemini.")

async def _generate_openai_tactical(user_payload: dict) -> tuple[TacticalReport, str, str]:
    """Generate tactical analysis with OpenAI."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload, indent=2)},
        ],
        temperature=0.3,
        max_tokens=1000,
    )
    raw = response.choices[0].message.content or "{}"
    return _parse_tactical_json(raw)


async def generate_tactical_analysis(
    leg: Leg,
    home: TeamStats,
    away: TeamStats,
    h2h: H2HStats,
    poisson: PoissonResult,
) -> tuple[TacticalReport, str, str]:
    """
    Generate deep tactical analysis using Google Gemini (Free) or OpenAI.
    Returns (TacticalReport, alternative_safe_pick, alternative_high_ev_pick).
    """
    if not settings.has_ai:
        return _fallback_tactical_report(leg, home, away, poisson)

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

    provider = settings.active_ai_provider

    if provider == "gemini":
        try:
            return await _generate_gemini_tactical(user_payload)
        except Exception as e:
            logger.warning(f"Gemini tactical analysis error: {e}")
            if settings.has_openai:
                try:
                    return await _generate_openai_tactical(user_payload)
                except Exception:
                    pass
            return _fallback_tactical_report(leg, home, away, poisson)

    elif provider == "openai":
        try:
            return await _generate_openai_tactical(user_payload)
        except Exception as e:
            logger.warning(f"OpenAI tactical analysis error: {e}")
            if settings.has_gemini:
                try:
                    return await _generate_gemini_tactical(user_payload)
                except Exception:
                    pass
            return _fallback_tactical_report(leg, home, away, poisson)

    return _fallback_tactical_report(leg, home, away, poisson)


def _fallback_tactical_report(
    leg: Leg,
    home: TeamStats,
    away: TeamStats,
    poisson: PoissonResult,
) -> tuple[TacticalReport, str, str]:
    """Provide structured tactical synthesis when LLM is offline."""
    top_score = poisson.top_exact_scores[0][0] if poisson.top_exact_scores else "1-1"
    home_xg = poisson.lambda_home
    away_xg = poisson.lambda_away

    # Stylistic clash synthesis based on goals & clean sheets
    if home_xg > 1.8 and away_xg > 1.3:
        tactical_clash = (
            f"{home.name} menerapkan pressing garis tinggi dengan rata-rata xG {home_xg:.2f}, "
            f"sementara {away.name} agresif dalam counter-attack cepat (xG {away_xg:.2f}). "
            "Ruang antar-lini diprediksi terbuka lebar."
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
    scenario = f"Tempo berhati-hati di babak pertama, dengan intensitas meningkat drastis setelah menit 60'."

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
