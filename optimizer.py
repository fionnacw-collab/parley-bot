"""
optimizer.py — Intelligent Parlay Slip Optimizer & Trap Eliminator.
Separates multi-leg slips into:
1. Conservative Safe Package (Low-risk anchor combos)
2. Maximum Value Sharp Package (High +EV value combos)
3. Traps & False Favorites to eliminate from your betting ticket.
"""

from __future__ import annotations

import math
from models import DeepMatchAnalysis, OptimizedParlayPackage, ParlayAnalysisReport


def optimize_parlay(report: ParlayAnalysisReport) -> OptimizedParlayPackage:
    """
    Analyze all matches in a parlay report and construct optimized betting sub-packages.
    """
    matches = report.matches
    if not matches:
        return OptimizedParlayPackage(
            safe_legs=[],
            safe_odds=1.0,
            safe_win_prob=0.0,
            safe_kelly_stake=0.0,
            value_legs=[],
            value_odds=1.0,
            value_expected_value=0.0,
            value_kelly_stake=0.0,
            trapped_legs=[],
        )

    # 1. Identify Traps & High Risk Legs
    trapped: list[tuple[DeepMatchAnalysis, list[str]]] = []
    clean_matches: list[DeepMatchAnalysis] = []

    for m in matches:
        reasons = []
        if m.expected_value < -0.04:
            reasons.append(f"Margin bandar terlalu tebal (Nilai -EV: {m.expected_value*100:.1f}%)")
        if m.true_probability < 0.40 and m.leg.odds < 2.20:
            reasons.append(f"Peluang menang rendah ({int(m.true_probability*100)}%) tidak sebanding dengan odds")
        if m.is_trap_candidate:
            reasons.extend(m.trap_reasons or ["Indikasi jebakan bias publik / pergerakan pasar mencurigakan"])

        if reasons:
            trapped.append((m, reasons))
        else:
            clean_matches.append(m)

    # If all matches were flagged or too few clean matches, allow top picks with warnings
    pool_for_safe = clean_matches if len(clean_matches) >= 2 else matches
    pool_for_value = clean_matches if len(clean_matches) >= 2 else matches

    # 2. Build Conservative Safe Package (2-3 highest win probability legs)
    sorted_by_prob = sorted(pool_for_safe, key=lambda x: x.true_probability, reverse=True)
    safe_legs = sorted_by_prob[: min(3, len(sorted_by_prob))]

    safe_odds = 1.0
    safe_win_prob = 1.0
    for leg in safe_legs:
        safe_odds *= leg.leg.odds
        safe_win_prob *= leg.true_probability

    # Calculate conservative Kelly stake (Fractional 0.20)
    # Kelly = (b*p - q) / b
    b_safe = safe_odds - 1.0
    if b_safe > 0:
        raw_kelly_safe = (b_safe * safe_win_prob - (1.0 - safe_win_prob)) / b_safe
        safe_kelly_stake = max(0.01, min(0.10, raw_kelly_safe * 0.20))
    else:
        safe_kelly_stake = 0.02

    # 3. Build Maximum Value Sharp Package (Legs with highest +EV)
    sorted_by_ev = sorted(pool_for_value, key=lambda x: x.expected_value, reverse=True)
    value_legs = [m for m in sorted_by_ev if m.expected_value >= -0.01][: min(4, len(sorted_by_ev))]
    if not value_legs:
        value_legs = sorted_by_ev[: min(2, len(sorted_by_ev))]

    value_odds = 1.0
    val_win_prob = 1.0
    for leg in value_legs:
        value_odds *= leg.leg.odds
        val_win_prob *= leg.true_probability

    val_ev = (value_odds * val_win_prob) - 1.0
    b_val = value_odds - 1.0
    if b_val > 0 and val_ev > 0:
        raw_kelly_val = (b_val * val_win_prob - (1.0 - val_win_prob)) / b_val
        value_kelly_stake = max(0.01, min(0.08, raw_kelly_val * 0.25))
    else:
        value_kelly_stake = 0.015

    return OptimizedParlayPackage(
        safe_legs=safe_legs,
        safe_odds=round(safe_odds, 2),
        safe_win_prob=safe_win_prob,
        safe_kelly_stake=round(safe_kelly_stake, 4),
        value_legs=value_legs,
        value_odds=round(value_odds, 2),
        value_expected_value=round(val_ev, 4),
        value_kelly_stake=round(value_kelly_stake, 4),
        trapped_legs=trapped,
    )
