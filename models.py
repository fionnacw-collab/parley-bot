"""
models.py — High-precision dataclasses and domain models for deep football & parlay analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MarketCategory(str, Enum):
    MATCH_WINNER = "1X2"
    OVER_UNDER = "Over/Under"
    BTTS = "Both Teams to Score"
    HANDICAP = "Handicap"
    DOUBLE_CHANCE = "Double Chance"
    OTHER = "General Market"


@dataclass
class Leg:
    home: str
    away: str
    pick: str
    odds: float
    market: MarketCategory = MarketCategory.OTHER
    raw: str = ""

    def clean_title(self) -> str:
        return f"{self.home} vs {self.away}"

    def infer_market(self) -> MarketCategory:
        p_lower = self.pick.lower()
        if "over" in p_lower or "under" in p_lower or "o/u" in p_lower:
            return MarketCategory.OVER_UNDER
        if "btts" in p_lower or "gg" in p_lower or "both teams" in p_lower:
            return MarketCategory.BTTS
        if "hdp" in p_lower or "handicap" in p_lower or "+" in p_lower or "-" in p_lower:
            return MarketCategory.HANDICAP
        if "1x" in p_lower or "x2" in p_lower or "12" in p_lower or "double chance" in p_lower:
            return MarketCategory.DOUBLE_CHANCE
        if "win" in p_lower or "home" in p_lower or "away" in p_lower or "draw" in p_lower:
            return MarketCategory.MATCH_WINNER
        return MarketCategory.OTHER


@dataclass
class PoissonResult:
    lambda_home: float
    lambda_away: float
    prob_home_win: float
    prob_draw: float
    prob_away_win: float
    prob_over_15: float
    prob_over_25: float
    prob_under_25: float
    prob_over_35: float
    prob_btts_yes: float
    prob_btts_no: float
    top_exact_scores: list[tuple[str, float]] = field(default_factory=list)


@dataclass
class MarketOddsData:
    best_odds: float = 0.0
    avg_odds: float = 0.0
    implied_prob: float = 0.0
    no_vig_prob: float = 0.0
    fair_odds: float = 0.0
    bookmaker_count: int = 1
    pinnacle_odds: float = 0.0
    fair_odds_zerovig: float = 0.0
    consensus_implied_prob: float = 0.0
    margin_percentage: float = 0.0
    is_value_bet: bool = False
    expected_value_pct: float = 0.0


@dataclass
class TeamStats:
    name: str
    team_id: int = 0
    form_str: str = "W-D-W-L-W"
    wins: int = 2
    draws: int = 2
    losses: int = 1
    form_points: int = 10
    goals_scored_avg: float = 1.5
    goals_conceded_avg: float = 1.0
    clean_sheet_pct: float = 0.35
    failed_to_score_pct: float = 0.20
    xg_for_avg: float = 1.45
    xg_against_avg: float = 1.05
    league_rank: int = 4
    total_played: int = 20
    is_fallback: bool = False
    recent_matches: list[dict] = field(default_factory=list)


@dataclass
class H2HStats:
    team1_wins: int = 0
    team2_wins: int = 0
    home_wins: int = 0
    draws: int = 0
    away_wins: int = 0
    total_matches: int = 0
    avg_total_goals: float = 2.5
    btts_rate: float = 0.5
    over_25_rate: float = 0.5
    btts_count: int = 0
    over_25_count: int = 0
    is_fallback: bool = False
    recent_scores: list[str] = field(default_factory=list)


@dataclass
class TacticalReport:
    summary: str = ""
    tactical_clash: str = ""
    squad_injuries_impact: str = ""
    fatigue_and_schedule: str = ""
    key_vulnerabilities: str = ""
    trap_warning: str = ""
    scenario_prediction: str = ""


@dataclass
class DeepMatchAnalysis:
    leg: Leg
    home_stats: TeamStats
    away_stats: TeamStats
    h2h: H2HStats
    poisson: PoissonResult
    odds_data: MarketOddsData = field(default_factory=MarketOddsData)
    tactical: TacticalReport = field(default_factory=TacticalReport)

    # Mathematical Outputs
    true_probability: float = 0.0
    bookie_implied_prob: float = 0.0
    fair_odds: float = 0.0
    expected_value: float = 0.0  # +EV in percentage, e.g. +0.07 (+7%)
    edge_pct: float = 0.0
    confidence_score: float = 0.0  # 0.0 - 100.0
    kelly_fractional_stake: float = 0.035
    kelly_stake_pct: float = 0.035
    verdict: str = "VALUE"
    risk_level: str = "MEDIUM"  # LOW, MEDIUM, HIGH, EXTREME
    parlay_role: str = "ANCHOR"
    is_trap_candidate: bool = False
    trap_reasons: list[str] = field(default_factory=list)

    # Alternative Angle
    alternative_safe_pick: str = ""
    alternative_high_ev_pick: str = ""

    def __post_init__(self):
        if self.fair_odds == 0.0 and self.true_probability > 0:
            self.fair_odds = round(1.0 / self.true_probability, 2)
        if self.kelly_fractional_stake == 0.035 and self.kelly_stake_pct != 0.035:
            self.kelly_fractional_stake = self.kelly_stake_pct
        if "TRAP" in self.verdict or self.expected_value < -0.05:
            self.is_trap_candidate = True


@dataclass
class ParlayAnalysisReport:
    matches: list[DeepMatchAnalysis]
    combined_user_odds: float = 1.0
    combined_odds: float = 1.0
    true_combined_prob: float = 0.0
    combined_true_probability: float = 0.0
    bookie_combined_prob: float = 0.0
    combined_fair_odds: float = 1.0
    parlay_expected_value: float = 0.0
    overall_expected_value: float = 0.0
    recommended_kelly_stake: float = 0.035
    recommended_units: float = 1.0
    overall_confidence: int = 75
    correlation_warnings: list[str] = field(default_factory=list)
    risk_tier: str = "MODERATE"
    core_anchor_leg: Leg | None = None
    executive_summary: str = ""

    def __post_init__(self):
        if self.combined_odds == 1.0 and self.combined_user_odds != 1.0:
            self.combined_odds = self.combined_user_odds
        elif self.combined_user_odds == 1.0 and self.combined_odds != 1.0:
            self.combined_user_odds = self.combined_odds

        if self.combined_true_probability == 0.0 and self.true_combined_prob != 0.0:
            self.combined_true_probability = self.true_combined_prob
        elif self.true_combined_prob == 0.0 and self.combined_true_probability != 0.0:
            self.true_combined_prob = self.combined_true_probability

        if self.overall_expected_value == 0.0 and self.parlay_expected_value != 0.0:
            self.overall_expected_value = self.parlay_expected_value
        elif self.parlay_expected_value == 0.0 and self.overall_expected_value != 0.0:
            self.parlay_expected_value = self.overall_expected_value

        if self.combined_fair_odds == 1.0 and self.combined_true_probability > 0:
            self.combined_fair_odds = round(1.0 / self.combined_true_probability, 2)

        # Set Core Anchor (Match with highest true probability)
        if self.matches and not self.core_anchor_leg:
            best_match = max(self.matches, key=lambda m: m.true_probability)
            self.core_anchor_leg = best_match.leg


# ---------------------------------------------------------------------------
# New Feature Domain Models: Top Picks, Staking, Optimizer, & Tracker
# ---------------------------------------------------------------------------

class TopPickCategory(str, Enum):
    SAFE_ANCHOR = "🛡️ Safe Anchor (Paling Stabil)"
    HIGH_EV = "💎 High +EV Value Bet"
    GOALS_OVER_UNDER = "⚽ Best Goals / Over-Under"
    HANDICAP_EDGE = "🚩 Asian Handicap Edge"


@dataclass
class TopPickItem:
    id: str
    match_title: str
    league: str
    kickoff: str
    pick: str
    odds: float
    market: MarketCategory
    category: TopPickCategory
    win_probability: float
    expected_value: float
    confidence_pct: int
    tactical_rationale: str
    key_stat: str


@dataclass
class OptimizedParlayPackage:
    # 1. Conservative Safe Package (2-3 highest probability legs)
    safe_legs: list[DeepMatchAnalysis]
    safe_odds: float
    safe_win_prob: float
    safe_kelly_stake: float

    # 2. Maximum Value Sharp Package (High +EV legs)
    value_legs: list[DeepMatchAnalysis]
    value_odds: float
    value_expected_value: float
    value_kelly_stake: float

    # 3. Traps / High-Risk Legs to Eliminate
    trapped_legs: list[tuple[DeepMatchAnalysis, list[str]]]


@dataclass
class TrackedBet:
    id: int
    user_id: int
    ticket_title: str
    legs_summary: str
    odds: float
    stake_amount: float
    potential_return: float
    status: str  # 'PENDING', 'WIN', 'LOSE', 'VOID'
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
