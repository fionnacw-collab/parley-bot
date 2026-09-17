"""
models.py — Domain Data Models for SBOBET AI Match & Parlay Suite (HDP, O/U, 1X2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SbobetMarketType(str, Enum):
    ASIAN_HANDICAP = "🚩 Asian Handicap (HDP)"
    OVER_UNDER = "⚽ Over / Under (O/U)"
    MATCH_WINNER = "👑 1X2 / Double Chance"


@dataclass
class ExtractedMatch:
    home: str
    away: str
    user_pick: str = ""
    user_odds: float = 0.0
    league: str = ""

    def clean_title(self) -> str:
        return f"{self.home} vs {self.away}"


@dataclass
class PoissonProjection:
    home_xg: float
    away_xg: float
    prob_home_win: float
    prob_draw: float
    prob_away_win: float
    prob_over_15: float
    prob_over_25: float
    prob_under_25: float
    prob_over_35: float
    top_exact_scores: list[tuple[str, float]] = field(default_factory=list)


@dataclass
class SbobetMarketRecommendation:
    market_type: SbobetMarketType
    selection: str  # e.g. "Arsenal -0.75", "Over 2.5 Goals", "Arsenal Win", "Inter 0.0 (Lek-Lekan)"
    projected_odds: float  # Decimal odds e.g. 1.90
    sbobet_line_display: str  # e.g. "Voor 3/4 (-1.08)", "O/U 2.5 (1.02)", "Handicap 0.0 (1.00)"
    win_probability: float  # e.g. 0.65
    expected_value: float  # e.g. +0.148 (+14.8% EV)
    confidence_pct: int  # e.g. 84
    is_main_best_pick: bool = False
    reasoning: str = ""


@dataclass
class DeepMatchAnalysis:
    match: ExtractedMatch
    poisson: PoissonProjection
    best_sbobet_pick: SbobetMarketRecommendation
    all_sbobet_markets: list[SbobetMarketRecommendation]
    predicted_score: str = ""
    tactical_summary: str = ""
    tactical_clash: str = ""
    key_weakness: str = ""
    trap_warning: str = ""
    is_trap: bool = False
    recommended_stake_pct: float = 0.035  # e.g. 3.5% of bankroll


@dataclass
class ParlayAnalysisReport:
    matches: list[DeepMatchAnalysis]
    combined_odds: float = 1.0
    combined_true_probability: float = 0.0
    combined_fair_odds: float = 1.0
    overall_expected_value: float = 0.0
    recommended_kelly_stake: float = 0.035
    risk_tier: str = "MODERATE"
    executive_summary: str = ""


@dataclass
class TrackedSlip:
    id: int
    user_id: int
    slip_title: str
    matches_json: str  # JSON list of match objects with home, away, pick, odds, live_score, status
    total_odds: float
    stake_amount: float
    potential_return: float
    status: str  # 'PENDING', 'LIVE', 'WIN', 'LOSE', 'VOID'
    live_status_summary: str  # e.g. "FT: 2-1 (Tiket WIN ✅)"
    created_at: str
    settled_at: str = ""
    profit_loss: float = 0.0


@dataclass
class UserStats:
    total_bets: int = 0
    wins: int = 0
    losses: int = 0
    voids: int = 0
    pending: int = 0
    total_staked: float = 0.0
    total_return: float = 0.0
    net_profit: float = 0.0
    win_rate_pct: float = 0.0
    roi_pct: float = 0.0
    current_streak: str = "0"
