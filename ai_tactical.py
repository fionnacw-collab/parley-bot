"""
ai_tactical.py — Deep qualitative tactical analysis powered by OpenAI GPT-4o.
Analyzes stylistic clashes, tactical matchups, motivation, fatigue, squad depth, and betting traps.
"""

from __future__ import annotations

import json
import logging
from openai import AsyncOpenAI

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


async def generate_tactical_analysis(
    leg: Leg,
    home: TeamStats,
    away: TeamStats,
    h2h: H2HStats,
    poisson: PoissonResult,
) -> tuple[TacticalReport, str, str]:
    """
    Generate deep tactical analysis using OpenAI GPT-4o-mini.
    Returns (TacticalReport, alternative_safe_pick, alternative_high_ev_pick).
    """
    if not settings.has_openai:
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

    try:
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

        raw = response.choices[0].message.content.strip()
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

    except Exception as e:
        logger.warning(f"OpenAI tactical analysis error: {e}")
        return _fallback_tactical_report(leg, home, away, poisson)


def _fallback_tactical_report(
    leg: Leg,
    home: TeamStats,
    away: TeamStats,
    poisson: PoissonResult,
) -> tuple[TacticalReport, str, str]:
    """Provide structured tactical synthesis when LLM is offline."""
    top_score = poisson.top_exact_scores[0][0] if poisson.top_exact_scores else "1-1"

    summary = (
        f"{home.name} (Form: {home.form_str}) menjamu {away.name} (Form: {away.form_str}). "
        f"Model memproyeksikan xG {poisson.lambda_home:.2f} vs {poisson.lambda_away:.2f} "
        f"dengan skor probabilitas tertinggi {top_score}."
    )

    tactical_clash = (
        f"{home.name} cenderung mengontrol penguasaan bola di kandang dengan rata-rata {home.goals_scored_avg:.1f} gol/laga. "
        f"{away.name} mengandalkan struktur transisi cepat namun rentan kebobolan {away.goals_conceded_avg:.1f} gol saat tandang."
    )

    squad_impact = (
        "Rotasi di lini tengah dan kebugaran bek sayap menjadi faktor krusial dalam meredam transisi balik lawan."
    )

    fatigue = (
        "Pertandingan krusial di jadwal kompetisi menuntut intensitas tinggi; tim dengan kedalaman bangku cadangan lebih unggul."
    )

    vulnerabilities = (
        f"Sisi kiri pertahanan {away.name} kerap tereksploitasi ketika menghadapi pressing tinggi terorganisir."
    )

    trap_warning = (
        f"Waspadai pergerakan odds pasar pada {leg.pick}. Jangan terpaku pada nama besar tanpa menghitung margin bandar."
    )

    scenario = (
        f"Babak pertama diprediksi berlangsung taktis dan berhati-hati. Peluang gol meningkat signifikan di babak kedua "
        f"saat stamina lini bertahan mulai menurun."
    )

    safe_pick = "Under 3.5" if poisson.prob_over_25 < 0.55 else "Over 1.5"
    high_ev = f"{home.name} Win & Over 1.5" if poisson.prob_home_win > 0.50 else "BTTS Yes"

    return (
        TacticalReport(
            summary=summary,
            tactical_clash=tactical_clash,
            squad_injuries_impact=squad_impact,
            fatigue_and_schedule=fatigue,
            key_vulnerabilities=vulnerabilities,
            trap_warning=trap_warning,
            scenario_prediction=scenario,
        ),
        safe_pick,
        high_ev,
    )
