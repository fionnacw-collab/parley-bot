"""
formatter.py — Rich Telegram Markdown formatter and interactive Inline Keyboard builder.
Formats deep mathematical models, Poisson xG, market consensus, and AI tactical insights.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from models import DeepMatchAnalysis, ParlayAnalysisReport


def _progress_bar(percentage: float, length: int = 10) -> str:
    """Generate visual ASCII progress bar [████░░░░░░]."""
    clamped = max(0.0, min(100.0, percentage))
    filled = int(round((clamped / 100.0) * length))
    empty = length - filled
    return f"[{'█' * filled}{'░' * empty}]"


def format_parlay_overview(report: ParlayAnalysisReport) -> tuple[str, InlineKeyboardMarkup]:
    """
    Format the primary executive summary and parlay dashboard with interactive match buttons.
    """
    lines: list[str] = []
    lines.append("🏆 *DEEP FOOTBALL & PARLAY ANALYZER* 🏆")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"📊 *Ringkasan Tiket:* {len(report.matches)} Pertandingan")
    lines.append(f"💰 *Combined Odds:* `@{report.combined_user_odds:.2f}`")
    lines.append(
        f"🎯 *True Win Probability:* `{report.true_combined_prob * 100:.1f}%` "
        f"_(Bandar Implied: {report.bookie_combined_prob * 100:.1f}%)_"
    )

    ev_sign = "+" if report.parlay_expected_value > 0 else ""
    ev_color = "🟢" if report.parlay_expected_value > 0.05 else ("🟡" if report.parlay_expected_value >= 0 else "🔴")
    lines.append(f"{ev_color} *Parlay EV:* `{ev_sign}{report.parlay_expected_value * 100:.1f}%`")
    lines.append(
        f"🛡️ *Rekomendasi Staking:* `{report.recommended_units:.2f} Unit` "
        f"_(Confidence: {report.overall_confidence}%)_"
    )
    lines.append("")
    lines.append(f"📝 *Analisis Eksekutif:*\n_{report.executive_summary}_")

    if report.correlation_warnings:
        lines.append("")
        for w in report.correlation_warnings:
            lines.append(w)

    lines.append("")
    lines.append("📋 *DAFTAR & PERFORMA SETIAP LAGA:*")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    keyboard_buttons: list[list[InlineKeyboardButton]] = []

    for i, m in enumerate(report.matches, start=1):
        leg = m.leg
        ev_str = f"{'+' if m.expected_value > 0 else ''}{m.expected_value * 100:.1f}% EV"
        bar = _progress_bar(m.true_probability * 100, length=8)

        lines.append(f"*{i}. {leg.home} vs {leg.away}*")
        lines.append(f"   🎯 Pick: `{leg.pick}` @`{leg.odds:.2f}` | {m.verdict}")
        lines.append(f"   📈 True Prob: `{m.true_probability * 100:.1f}%` {bar} | `{ev_str}`")
        lines.append(f"   🏷️ Peran: *{m.parlay_role}* | Resiko: `{m.risk_level}`")
        lines.append("")

        # Add button for this match
        btn_text = f"🔍 #{i} {leg.home[:10]} vs {leg.away[:10]}"
        keyboard_buttons.append([InlineKeyboardButton(btn_text, callback_data=f"match_{i-1}")])

    lines.append("👇 *Pilih tombol di bawah untuk melihat analisis mendalam per laga:*")

    reply_markup = InlineKeyboardMarkup(keyboard_buttons)
    return "\n".join(lines), reply_markup


def format_single_match_deep_dive(
    analysis: DeepMatchAnalysis,
    index: int,
    total: int,
) -> tuple[str, InlineKeyboardMarkup]:
    """
    Format ultra-detailed mathematical, tactical, and market analysis for a single match.
    """
    m = analysis
    leg = m.leg
    p = m.poisson
    t = m.tactical

    lines: list[str] = []
    lines.append(f"⚽ *ANALISIS MENDALAM LAGA #{index + 1} / {total}*")
    lines.append(f"⚔️ *{leg.home}* vs *{leg.away}*")
    lines.append(f"🎯 *Pilihan Taruhan:* `{leg.pick}` @`{leg.odds:.2f}` ({leg.market.value})")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # 1. Math & Value
    lines.append("📈 *1. METRIK MATEMATIKA & VALUE:*")
    lines.append(f"• Status: *{m.verdict}*")
    ev_sign = "+" if m.expected_value > 0 else ""
    lines.append(f"• Expected Value (EV): *{ev_sign}{m.expected_value * 100:.1f}%*")
    lines.append(f"• Probabilitas Riil Model: *{m.true_probability * 100:.1f}%*")
    lines.append(f"• Implied Odds Bandar: *{m.bookie_implied_prob * 100:.1f}%*")
    lines.append(f"• Keunggulan vs Bandar (Edge): *{'+' if m.edge_pct > 0 else ''}{m.edge_pct * 100:.1f}%*")
    lines.append(f"• Kelly Staking: *{m.kelly_stake_pct * 100:.2f}% Bankroll*")
    lines.append(f"• Confidence Score: *{m.confidence_score}%* {_progress_bar(m.confidence_score, 8)}")
    lines.append("")

    # 2. Poisson & Expected Goals (xG)
    lines.append("📐 *2. MODEL POISSON & EXPECTED GOALS (xG):*")
    lines.append(f"• Proyeksi xG: *{leg.home} {p.lambda_home:.2f}* - *{p.lambda_away:.2f} {leg.away}*")
    lines.append(
        f"• Probabilitas 1X2: Home *{p.prob_home_win * 100:.1f}%* | "
        f"Draw *{p.prob_draw * 100:.1f}%* | Away *{p.prob_away_win * 100:.1f}%*"
    )
    lines.append(
        f"• Pasar Gol: Over 2.5 *{p.prob_over_25 * 100:.1f}%* | Under 2.5 *{p.prob_under_25 * 100:.1f}%*"
    )
    lines.append(
        f"• BTTS: Yes *{p.prob_btts_yes * 100:.1f}%* | No *{p.prob_btts_no * 100:.1f}%*"
    )
    if p.top_exact_scores:
        scores_str = ", ".join([f"`{s[0]}` ({s[1]}%)" for s in p.top_exact_scores[:4]])
        lines.append(f"• Skor Paling Realistis: {scores_str}")
    lines.append("")

    # 3. Market & Sharp Odds
    if m.odds_data:
        od = m.odds_data
        lines.append("🏦 *3. KONSENSUS PASAR & SHARP ODDS:*")
        lines.append(f"• Rata-rata Pasar: `@{od.avg_odds:.2f}` | Best Odds: `@{od.best_odds:.2f}`")
        if od.pinnacle_odds > 0:
            lines.append(f"• Pinnacle (Sharp Benchmark): `@{od.pinnacle_odds:.2f}`")
        lines.append(f"• Fair Odds (Nol Margin): `@{od.fair_odds:.2f}`")
        lines.append("")

    # 4. Form & H2H
    lines.append("📊 *4. KONDISI TREN & HEAD-TO-HEAD:*")
    lines.append(f"• {m.home_stats.name} Form: `{m.home_stats.form_str}` (Gol: {m.home_stats.goals_scored_avg:.1f} / laga)")
    lines.append(f"• {m.away_stats.name} Form: `{m.away_stats.form_str}` (Kebobolan: {m.away_stats.goals_conceded_avg:.1f} / laga)")
    if m.h2h.total_matches > 0:
        lines.append(
            f"• H2H Terakhir ({m.h2h.total_matches} laga): "
            f"H:{m.h2h.home_wins} D:{m.h2h.draws} A:{m.h2h.away_wins} | "
            f"Over 2.5: {int(m.h2h.over_25_pct * 100)}% | BTTS: {int(m.h2h.btts_pct * 100)}%"
        )
    lines.append("")

    # 5. Tactical Analysis (AI)
    lines.append("🧠 *5. LAPORAN TAKTIK & MATCHUP:*")
    if t.tactical_clash:
        lines.append(f"• *Benturan Gaya:* {t.tactical_clash}")
    if t.key_vulnerabilities:
        lines.append(f"• *Celah Pertahanan:* {t.key_vulnerabilities}")
    if t.trap_warning:
        lines.append(f"• *⚠️ Jebakan Bandar:* {t.trap_warning}")
    if t.scenario_prediction:
        lines.append(f"• *Alur Pertandingan:* {t.scenario_prediction}")
    lines.append("")

    # 6. Alternative Recommendations
    lines.append("🎯 *6. REKOMENDASI OPSI LAIN:*")
    if m.alternative_safe_pick:
        lines.append(f"• 🛡️ *Opsi Lebih Aman:* `{m.alternative_safe_pick}`")
    if m.alternative_high_ev_pick:
        lines.append(f"• 🚀 *Opsi High Value:* `{m.alternative_high_ev_pick}`")

    # Navigation buttons
    nav_row: list[InlineKeyboardButton] = []
    if index > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Sebelumnya", callback_data=f"match_{index - 1}"))
    if index < total - 1:
        nav_row.append(InlineKeyboardButton("Berikutnya ➡️", callback_data=f"match_{index + 1}"))

    buttons = []
    if nav_row:
        buttons.append(nav_row)
    buttons.append([InlineKeyboardButton("📋 Kembali ke Ringkasan Parlay", callback_data="back_summary")])

    reply_markup = InlineKeyboardMarkup(buttons)
    return "\n".join(lines), reply_markup
