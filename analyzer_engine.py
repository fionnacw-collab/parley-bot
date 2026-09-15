"""
analyzer_engine.py — Master orchestrator for deep quantitative and qualitative football analysis.
Combines real-time data, Poisson models, bookmaker market vig removal, AI tactics, and Kelly staking.
"""

from __future__ import annotations

import asyncio
import logging
from config import settings
from models import (
    DeepMatchAnalysis,
    Leg,
    ParlayAnalysisReport,
)
from football_api import fetch_full_match_context
from odds_api import fetch_market_odds
from statistical_model import (
    calculate_expected_goals,
    calculate_expected_value,
    calculate_fractional_kelly,
    compute_poisson_distribution,
    evaluate_bet_verdict,
    match_leg_to_true_prob,
)
from ai_tactical import generate_tactical_analysis

logger = logging.getLogger(__name__)


async def analyze_single_leg(leg: Leg) -> DeepMatchAnalysis:
    """
    Perform deep statistical, tactical, and market analysis on a single match leg.
    """
    # 1. Fetch live football context (Form, H2H, Goals)
    home_stats, away_stats, h2h = await fetch_full_match_context(leg.home, leg.away)

    # 2. Compute Poisson xG & Outcome Probabilities
    lambda_h, lambda_a = calculate_expected_goals(home_stats, away_stats, h2h)
    poisson = compute_poisson_distribution(lambda_h, lambda_a)

    # 3. Fetch Bookmaker Market Odds & Sharp Benchmark (run in parallel with AI tactics)
    odds_task = fetch_market_odds(leg.home, leg.away, leg.pick, leg.market, leg.odds)
    tactical_task = generate_tactical_analysis(leg, home_stats, away_stats, h2h, poisson)

    odds_data, (tactical_report, safe_alt, high_ev_alt) = await asyncio.gather(odds_task, tactical_task)

    # 4. Resolve True Probability & Bookmaker Metrics
    true_prob = match_leg_to_true_prob(leg, poisson, odds_data)
    bookie_implied = round(1.0 / leg.odds, 4) if leg.odds > 0 else 0.50

    # 5. Expected Value & Edge
    ev = calculate_expected_value(true_prob, leg.odds)
    edge = round(true_prob - bookie_implied, 4)

    # 6. Fractional Kelly Staking
    kelly_stake = calculate_fractional_kelly(true_prob, leg.odds, fraction=settings.default_fractional_kelly)

    # 7. Confidence Score (0-100)
    # Balanced blend of true probability, edge, and form reliability
    base_confidence = int(true_prob * 100)
    edge_adjustment = int(edge * 100 * 0.5)
    confidence = max(25, min(95, base_confidence + edge_adjustment))

    # 8. Rating & Verdict
    verdict, risk_level, parlay_role = evaluate_bet_verdict(ev, edge, confidence)

    return DeepMatchAnalysis(
        leg=leg,
        poisson=poisson,
        odds_data=odds_data,
        home_stats=home_stats,
        away_stats=away_stats,
        h2h=h2h,
        tactical=tactical_report,
        true_probability=round(true_prob, 4),
        bookie_implied_prob=bookie_implied,
        expected_value=ev,
        edge_pct=edge,
        kelly_stake_pct=kelly_stake,
        confidence_score=confidence,
        verdict=verdict,
        risk_level=risk_level,
        parlay_role=parlay_role,
        alternative_safe_pick=safe_alt,
        alternative_high_ev_pick=high_ev_alt,
    )


async def analyze_parlay(legs: list[Leg]) -> ParlayAnalysisReport:
    """
    Analyze all legs of a parlay concurrently, calculate compound probabilities,
    detect correlations, and generate bankroll recommendations.
    """
    if not legs:
        raise ValueError("Tidak ada pertandingan untuk dianalisis.")

    # Execute all match analyses in parallel
    matches: list[DeepMatchAnalysis] = await asyncio.gather(
        *(analyze_single_leg(leg) for leg in legs)
    )

    combined_odds = 1.0
    true_combined_prob = 1.0
    bookie_combined_prob = 1.0

    for m in matches:
        combined_odds *= m.leg.odds
        true_combined_prob *= m.true_probability
        bookie_combined_prob *= m.bookie_implied_prob

    combined_odds = round(combined_odds, 2)
    true_combined_prob = round(true_combined_prob, 4)
    bookie_combined_prob = round(bookie_combined_prob, 4)

    # Overall Parlay Expected Value
    parlay_ev = round((true_combined_prob * combined_odds) - 1.0, 4)

    # Correlation and synergy checks
    warnings: list[str] = []
    seen_matches: dict[str, list[str]] = {}

    for m in matches:
        key = f"{m.leg.home.lower()} vs {m.leg.away.lower()}"
        if key not in seen_matches:
            seen_matches[key] = []
        seen_matches[key].append(m.leg.pick)

    for match_key, picks in seen_matches.items():
        if len(picks) > 1:
            warnings.append(
                f"⚠️ *Korelasi Tiket Sama:* {match_key} memiliki {len(picks)} pick ({', '.join(picks)}). "
                f"Pastikan bandar kamu mengizinkan Same Game Parlay (SGP)."
            )

    # Confidence aggregation
    avg_confidence = int(sum(m.confidence_score for m in matches) / len(matches))

    # Bankroll unit sizing
    if parlay_ev > 0.05 and true_combined_prob > 0.20:
        recommended_units = 1.5
    elif parlay_ev > 0.0:
        recommended_units = 1.0
    elif true_combined_prob > 0.35:
        recommended_units = 0.5
    else:
        recommended_units = 0.25

    # Executive Summary
    high_ev_count = sum(1 for m in matches if m.expected_value > 0)
    trap_count = sum(1 for m in matches if "TRAP" in m.verdict)

    exec_summary = (
        f"Tiket parlay ini berisi *{len(matches)} laga* dengan combined odds *{combined_odds:.2f}*. "
        f"Model menemukan *{high_ev_count} pick bernilai (+EV)* dan *{trap_count} pick terindikasi trap/margin tinggi*. "
        f"Probabilitas tembus riil diestimasi *{true_combined_prob * 100:.1f}%* "
        f"(vs implied bandar {bookie_combined_prob * 100:.1f}%)."
    )

    return ParlayAnalysisReport(
        matches=matches,
        combined_user_odds=combined_odds,
        true_combined_prob=true_combined_prob,
        bookie_combined_prob=bookie_combined_prob,
        parlay_expected_value=parlay_ev,
        correlation_warnings=warnings,
        overall_confidence=avg_confidence,
        recommended_units=recommended_units,
        executive_summary=exec_summary,
    )
