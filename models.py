"""
models.py — High-precision dataclasses and domain models for deep football analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MarketCategory(str, Enum):
    MATCH_WINNER = "1X2"
    OVER_UNDER = "Over/Under"
    BTTS = "Both Teams to Score"
    ASIAN_HANDICAP = "Handicap"
    DOUBLE_CHANCE = "Double Chance"
    DRAW_NO_BET = "Draw No Bet"
    OTHER = "General Market"


@dataclass
class Leg:
    home: str
    away: str
    pick: str
    odds: float
    market: MarketCategory = MarketCategory.OTHER
    line: float | None = None
    raw: str = ""

    def __post_init__(self):
        if self.market == MarketCategory.OTHER:
            self.market = self._detect_market(self.pick)

    @staticmethod
    def _detect_market(pick: str) -> MarketCategory:
        p = pick.lower().strip()
        if any(x in p for x in ["over", "under", "o/u", "total"]):
            return MarketCategory.OVER_UNDER
        if any(x in p for x in ["btts", "gg", "ng", "both teams", "kedua tim"]):
            return MarketCategory.BTTS
        if any(x in p for x in ["hdp", "handicap", "+", "-"]):
            return MarketCategory.ASIAN_HANDICAP
        if any(x in p for x in ["double chance", "1x", "x2", "12"]):
            return MarketCategory.DOUBLE_CHANCE
        if any(x in p for x in ["dnb", "draw no bet"]):
            return MarketCategory.DRAW_NO_BET
        if any(x in p for x in ["win", "ml", "home", "away", "draw", "seri", "menang"]):
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
    prob_over_35: float
    prob_under_25: float
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
    bookmaker_count: int = 0
    pinnacle_odds: float = 0.0


@dataclass
class TeamStats:
    name: str
    team_id: int = 0
    league: str = ""
    form_str: str = "N/A"
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_scored_avg: float = 1.35
    goals_conceded_avg: float = 1.25
    clean_sheet_pct: float = 0.25
    failed_to_score_pct: float = 0.20
    home_or_away_form: str = "N/A"
    recent_matches: list[dict] = field(default_factory=list)


@dataclass
class H2HStats:
    total_matches: int = 0
    home_wins: int = 0
    draws: int = 0
    away_wins: int = 0
    btts_pct: float = 0.50
    over_25_pct: float = 0.50
    avg_goals: float = 2.50
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
    poisson: PoissonResult
    odds_data: MarketOddsData | None
    home_stats: TeamStats
    away_stats: TeamStats
    h2h: H2HStats
    tactical: TacticalReport

    # Math & Value
    true_probability: float  # e.g. 0.58 = 58%
    bookie_implied_prob: float  # 1 / user_odds
    expected_value: float  # (true_prob * odds) - 1.0
    edge_pct: float  # true_prob - bookie_implied_prob
    kelly_stake_pct: float  # recommended bankroll percentage (0.0 to 0.05)
    confidence_score: int  # 0 to 100

    # Qualitative verdict
    verdict: str  # "STRONG VALUE", "MODERATE VALUE", "FAIR PRICE", "TRAP / NEGATIVE EV"
    risk_level: str  # "LOW", "MEDIUM", "HIGH", "EXTREME"
    parlay_role: str  # "CORE ANCHOR", "VALUE ROTATION", "AVOID / FILTER OUT"

    # Alternative suggestions
    alternative_safe_pick: str = ""
    alternative_high_ev_pick: str = ""


@dataclass
class ParlayAnalysisReport:
    matches: list[DeepMatchAnalysis]
    combined_user_odds: float
    true_combined_prob: float
    bookie_combined_prob: float
    parlay_expected_value: float
    correlation_warnings: list[str] = field(default_factory=list)
    overall_confidence: int = 50
    recommended_units: float = 1.0
    executive_summary: str = ""
