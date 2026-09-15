"""
statistical_model.py — Advanced mathematical modeling for football match outcomes.
Implements:
- Poisson distribution & xG (Expected Goals) scoreline matrix
- Market margin / vig removal (Shin / Proportional method)
- True probability calculation for 1X2, Over/Under, BTTS, and Asian Handicap
- Expected Value (+EV) and Fractional Kelly Criterion staking
"""

from __future__ import annotations

import math
from typing import Tuple
from models import (
    Leg,
    MarketCategory,
    MarketOddsData,
    PoissonResult,
    TeamStats,
    H2HStats,
)


def _poisson_pmf(k: int, lamb: float) -> float:
    """Calculate Poisson probability mass function P(X = k; lambda)."""
    if lamb <= 0:
        return 1.0 if k == 0 else 0.0
    return (math.pow(lamb, k) * math.exp(-lamb)) / math.factorial(k)


def calculate_expected_goals(
    home: TeamStats,
    away: TeamStats,
    h2h: H2HStats | None = None,
) -> Tuple[float, float]:
    """
    Estimate expected goals (lambda_home, lambda_away) based on attacking/defensive
    ratings, home advantage, and historical H2H trends.
    """
    # European football league baseline averages
    league_avg_home = 1.45
    league_avg_away = 1.15

    # Home team attacking strength & away defensive weakness
    home_attack = max(0.6, home.goals_scored_avg) / league_avg_home
    away_defense = max(0.6, away.goals_conceded_avg) / league_avg_home

    # Away team attacking strength & home defensive weakness
    away_attack = max(0.5, away.goals_scored_avg) / league_avg_away
    home_defense = max(0.5, home.goals_conceded_avg) / league_avg_away

    # Home advantage factor (typically 1.12 - 1.20)
    home_advantage = 1.15

    lambda_home = league_avg_home * home_attack * away_defense * home_advantage
    lambda_away = league_avg_away * away_attack * home_defense

    # Adjust with H2H trend if significant data exists
    if h2h and h2h.total_matches >= 3 and h2h.avg_goals > 0:
        h2h_weight = min(0.3, h2h.total_matches * 0.05)
        total_projected = lambda_home + lambda_away
        if total_projected > 0:
            scale = (h2h.avg_goals / total_projected) * h2h_weight + (1 - h2h_weight)
            lambda_home *= scale
            lambda_away *= scale

    # Keep within realistic football boundaries (0.3 to 4.5)
    lambda_home = max(0.35, min(4.5, round(lambda_home, 3)))
    lambda_away = max(0.25, min(4.0, round(lambda_away, 3)))

    return lambda_home, lambda_away


def compute_poisson_distribution(
    lambda_home: float,
    lambda_away: float,
    max_goals: int = 7,
) -> PoissonResult:
    """
    Generate bivariate Poisson distribution score matrix and derive all key market probabilities.
    """
    matrix: dict[tuple[int, int], float] = {}

    for h in range(max_goals + 1):
        p_h = _poisson_pmf(h, lambda_home)
        for a in range(max_goals + 1):
            p_a = _poisson_pmf(a, lambda_away)
            matrix[(h, a)] = p_h * p_a

    # Normalize matrix to 1.0 (since max_goals is truncated at 7)
    total_prob = sum(matrix.values())
    if total_prob > 0:
        for k in matrix:
            matrix[k] /= total_prob

    # Outcomes
    p_home_win = sum(p for (h, a), p in matrix.items() if h > a)
    p_draw = sum(p for (h, a), p in matrix.items() if h == a)
    p_away_win = sum(p for (h, a), p in matrix.items() if h < a)

    # Goal totals
    p_over_15 = sum(p for (h, a), p in matrix.items() if (h + a) > 1.5)
    p_over_25 = sum(p for (h, a), p in matrix.items() if (h + a) > 2.5)
    p_over_35 = sum(p for (h, a), p in matrix.items() if (h + a) > 3.5)
    p_under_25 = sum(p for (h, a), p in matrix.items() if (h + a) < 2.5)

    # BTTS
    p_btts_yes = sum(p for (h, a), p in matrix.items() if h >= 1 and a >= 1)
    p_btts_no = 1.0 - p_btts_yes

    # Top exact scores
    sorted_scores = sorted(matrix.items(), key=lambda x: x[1], reverse=True)[:5]
    top_scores = [(f"{h}-{a}", round(p * 100, 1)) for (h, a), p in sorted_scores]

    return PoissonResult(
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        prob_home_win=round(p_home_win, 4),
        prob_draw=round(p_draw, 4),
        prob_away_win=round(p_away_win, 4),
        prob_over_15=round(p_over_15, 4),
        prob_over_25=round(p_over_25, 4),
        prob_over_35=round(p_over_35, 4),
        prob_under_25=round(p_under_25, 4),
        prob_btts_yes=round(p_btts_yes, 4),
        prob_btts_no=round(p_btts_no, 4),
        top_exact_scores=top_scores,
    )


def strip_bookmaker_margin(odds_list: list[float]) -> list[float]:
    """
    Remove bookmaker overround (vig) from a 2-way or 3-way market using proportional method.
    Returns fair true probabilities [p1, p2, ...].
    """
    if not odds_list or any(o <= 1.0 for o in odds_list):
        return [1.0 / len(odds_list)] * len(odds_list) if odds_list else []

    implied_probs = [1.0 / o for o in odds_list]
    total_margin = sum(implied_probs)

    if total_margin <= 0:
        return implied_probs

    return [p / total_margin for p in implied_probs]


def match_leg_to_true_prob(
    leg: Leg,
    poisson: PoissonResult,
    odds_data: MarketOddsData | None = None,
) -> float:
    """
    Resolve the specific user pick into its true statistical probability.
    """
    pick_lower = leg.pick.lower()

    # 1. Over / Under
    if "over" in pick_lower or "o" in pick_lower and ("2.5" in pick_lower or "2 1/2" in pick_lower):
        if "1.5" in pick_lower:
            return poisson.prob_over_15
        elif "3.5" in pick_lower:
            return poisson.prob_over_35
        return poisson.prob_over_25

    if "under" in pick_lower or "u" in pick_lower and ("2.5" in pick_lower or "2 1/2" in pick_lower):
        if "1.5" in pick_lower:
            return 1.0 - poisson.prob_over_15
        elif "3.5" in pick_lower:
            return 1.0 - poisson.prob_over_35
        return poisson.prob_under_25

    # 2. Both Teams to Score (BTTS)
    if any(x in pick_lower for x in ["btts yes", "gg", "both teams to score", "kedua tim cetak gol"]):
        return poisson.prob_btts_yes
    if any(x in pick_lower for x in ["btts no", "ng", "tanpa kedua tim"]):
        return poisson.prob_btts_no

    # 3. Match Winner 1X2
    home_name = leg.home.lower()
    away_name = leg.away.lower()

    if any(x in pick_lower for x in ["draw", "seri", "x"]):
        return poisson.prob_draw

    # Check if home team win
    if (
        "home" in pick_lower
        or "1" == pick_lower.strip()
        or any(token in pick_lower for token in home_name.split() if len(token) > 3)
    ):
        return poisson.prob_home_win

    # Check if away team win
    if (
        "away" in pick_lower
        or "2" == pick_lower.strip()
        or any(token in pick_lower for token in away_name.split() if len(token) > 3)
    ):
        return poisson.prob_away_win

    # 4. Double Chance
    if "1x" in pick_lower or "home or draw" in pick_lower:
        return poisson.prob_home_win + poisson.prob_draw
    if "x2" in pick_lower or "draw or away" in pick_lower:
        return poisson.prob_away_win + poisson.prob_draw
    if "12" in pick_lower or "home or away" in pick_lower:
        return poisson.prob_home_win + poisson.prob_away_win

    # Fallback to no-vig market odds if available, otherwise implied probability
    if odds_data and odds_data.no_vig_prob > 0:
        return odds_data.no_vig_prob

    if leg.odds > 1.0:
        # Conservative haircut of 6% bookie vig
        return round((1.0 / leg.odds) * 0.94, 4)

    return 0.50


def calculate_expected_value(true_prob: float, odds: float) -> float:
    """
    Expected Value formula: EV = (True Probability * Decimal Odds) - 1.0
    Returns decimal EV (e.g. +0.082 means +8.2% EV).
    """
    if odds <= 1.0 or true_prob <= 0.0:
        return -1.0
    return round((true_prob * odds) - 1.0, 4)


def calculate_fractional_kelly(
    true_prob: float,
    odds: float,
    fraction: float = 0.25,
) -> float:
    """
    Fractional Kelly Criterion:
    f* = (b * p - q) / b
    where:
    b = decimal odds - 1
    p = true probability
    q = 1 - p
    fraction: Kelly fraction (default 0.25 for quarter-Kelly to protect bankroll).
    """
    if odds <= 1.0 or true_prob <= 0.0:
        return 0.0

    b = odds - 1.0
    p = true_prob
    q = 1.0 - p

    full_kelly = (b * p - q) / b

    if full_kelly <= 0:
        return 0.0

    recommended = full_kelly * fraction
    # Cap maximum stake at 5% of bankroll to maintain responsible gambling bounds
    return round(min(0.05, recommended), 4)


def evaluate_bet_verdict(ev: float, edge: float, confidence: int) -> tuple[str, str, str]:
    """
    Returns (verdict, risk_level, parlay_role).
    """
    if ev >= 0.07 and edge > 0.03 and confidence >= 70:
        return "🟢 STRONG VALUE (+EV)", "LOW", "CORE ANCHOR"
    elif ev >= 0.02 and edge >= 0.0 and confidence >= 60:
        return "🟡 MODERATE VALUE", "MEDIUM", "VALUE ROTATION"
    elif ev >= -0.04 and confidence >= 55:
        return "⚪ FAIR PLAY (NEUTRAL)", "MEDIUM", "SECONDARY LEVELED"
    else:
        return "🔴 TRAP / NEGATIVE EV", "HIGH", "AVOID / FILTER OUT"
