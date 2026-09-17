"""
formatter.py — Rich Telegram Markdown Formatter & Interactive Keyboard Builder.
Formats deep SBOBET market recommendations, Poisson scorelines, tactical trap warnings,
Rupiah staking calculations, and live match tracker dashboards.
"""

from __future__ import annotations

import json
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from models import (
    DeepMatchAnalysis,
    ExtractedMatch,
    ParlayAnalysisReport,
    SbobetMarketRecommendation,
    SbobetMarketType,
    TrackedSlip,
    UserStats,
)
import tracker


def _progress_bar(percentage: float, length: int = 10) -> str:
    """Generate visual ASCII progress bar [████░░░░░░]."""
    clamped = max(0.0, min(100.0, percentage))
    filled = int(round((clamped / 100.0) * length))
    empty = length - filled
    return f"[{'█' * filled}{'░' * empty}]"


def _format_rupiah(amount: float) -> str:
    """Format float into standard Indonesian Rupiah format (Rp X.XXX.XXX)."""
    val = int(round(amount))
    return f"Rp {val:,}".replace(",", ".")


# ---------------------------------------------------------------------------
# 1. Single Match Deep SBOBET Analysis Formatter
# ---------------------------------------------------------------------------

def format_single_match_analysis(
    analysis: DeepMatchAnalysis,
    user_id: int | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    """Format deep SBOBET analysis for a single fixture with all 4 market options."""
    bankroll = tracker.get_user_bankroll(user_id) if user_id else 1000000.0
    m = analysis.match
    p = analysis.poisson
    best = analysis.best_sbobet_pick

    stake_rp = bankroll * analysis.recommended_stake_pct
    profit_rp = (stake_rp * best.projected_odds) - stake_rp

    top_score = p.top_exact_scores[0][0] if p.top_exact_scores else "2 - 1"
    top_score_prob = int(p.top_exact_scores[0][1] * 100) if p.top_exact_scores else 15

    ev_sign = "+" if best.expected_value > 0 else ""
    ev_color = "🟢" if best.expected_value > 0.05 else ("🟡" if best.expected_value >= 0 else "🔴")

    lines = [
        f"⚽ *ANALISIS LAGA: {m.home.upper()} vs {m.away.upper()}*",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🎯 *Prediksi Skor Paling Mungkin:* `{top_score}` _(Peluang {top_score_prob}%)_",
        f"📊 *Proyeksi xG:* `{m.home} ({p.home_xg:.2f})` vs `({p.away_xg:.2f}) {m.away}`",
        f"{ev_color} *Status Peluang:* `+{best.expected_value*100:.1f}% EV (Nilai Bagus)`",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "⭐ *REKOMENDASI UTAMA SBOBET (AI BEST PICK):*",
        f"👉 *{best.selection}* @`{best.projected_odds:.2f}`",
        f"• 📋 Pasaran: `{best.sbobet_line_display}`",
        f"• 🎯 Win Prob: `{best.win_probability * 100:.1f}%` {_progress_bar(best.win_probability * 100, 8)}",
        f"• 💡 Alasan: _{best.reasoning}_",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "📋 *PILIHAN PASARAN SBOBET LAINNYA:*",
    ]

    for market in analysis.all_sbobet_markets:
        if market.market_type != best.market_type:
            lines.append(
                f"• *{market.market_type.value}:*\n"
                f"   Pilihan: `{market.selection}` @`{market.projected_odds:.2f}` _({market.sbobet_line_display})_\n"
                f"   Peluang: `{int(market.win_probability*100)}%` | EV: `+{market.expected_value*100:.1f}%`"
            )

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🧠 *ANALISIS TAKTIS & JEBAKAN BANDAR:*",
        f"• 📋 *Konteks:* {analysis.tactical_summary}",
        f"• ⚔️ *Benturan Taktik:* {analysis.tactical_clash}",
        f"• ⚠️ *Titik Lemah:* {analysis.key_weakness}",
        f"• 🚨 *Trap Alert:* {analysis.trap_warning}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "💵 *SARAN STAKING (MODAL " + _format_rupiah(bankroll) + "):*",
        f"• 💰 Rekomendasi Pasang: `{_format_rupiah(stake_rp)}` _({analysis.recommended_stake_pct*100:.1f}% Kelly)_",
        f"• 🎯 Estimasi Cuan Bersih: `+{_format_rupiah(profit_rp)}`",
    ])

    keyboard = [
        [InlineKeyboardButton("💾 Simpan ke Tracker & Pantau Skor", callback_data=f"track_save_single_0")],
        [
            InlineKeyboardButton("💵 Atur Modal Bankroll", callback_data="menu_bankroll"),
            InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_main"),
        ],
    ]

    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


# ---------------------------------------------------------------------------
# 2. Multi-Match Mix Parlay Formatter
# ---------------------------------------------------------------------------

def format_parlay_analysis(
    report: ParlayAnalysisReport,
    user_id: int | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    """Format an optimized Mix Parlay report constructed from SBOBET best picks."""
    bankroll = tracker.get_user_bankroll(user_id) if user_id else 1000000.0
    rec_stake = bankroll * report.recommended_kelly_stake
    pot_return = rec_stake * report.combined_odds
    net_profit = pot_return - rec_stake

    lines = [
        f"🏆 *REKOMENDASI TIKET MIX PARLAY SBOBET ({len(report.matches)} LAGA)* 🏆",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"💰 *Total Odds Tiket:* `@{report.combined_odds:.2f}`",
        f"🎯 *True Win Probability:* `{report.combined_true_probability * 100:.1f}%` {_progress_bar(report.combined_true_probability * 100, 8)}",
        f"⚖️ *Fair Odds (Bebas Komisi):* `@{report.combined_fair_odds:.2f}`",
        f"💎 *Overall +EV:* `+{report.overall_expected_value * 100:.1f}%`",
        f"🛡️ *Kategori Resiko:* `{report.risk_tier}`",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "💵 *REKOMENDASI PASANG RUPIAH:*",
        f"• 💼 Modal Kamu: `{_format_rupiah(bankroll)}`",
        f"• 💰 Saran Pasang (Kelly): `{_format_rupiah(rec_stake)}` _({report.recommended_kelly_stake*100:.1f}% modal)_",
        f"• 🎯 Estimasi Profit Bersih: `+{_format_rupiah(net_profit)}`",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📝 *Ringkasan Strategi:*\n_{report.executive_summary}_\n",
        "📋 *DAFTAR PASARAN PILIHAN AI SETIAP LAGA:*",
    ]

    keyboard_buttons: list[list[InlineKeyboardButton]] = []

    for idx, m in enumerate(report.matches, start=1):
        best = m.best_sbobet_pick
        lines.append(
            f"{idx}. *{m.match.clean_title()}*\n"
            f"   👉 *{best.selection}* @`{best.projected_odds:.2f}` _({best.sbobet_line_display})_\n"
            f"   Win Prob: `{int(best.win_probability*100)}%` | EV: `+{best.expected_value*100:.1f}%`"
        )
        btn_text = f"🔍 Bedah #{idx}: {m.match.home} vs {m.match.away}"
        keyboard_buttons.append([InlineKeyboardButton(btn_text, callback_data=f"drill_match_{idx-1}")])

    lines.append("")
    lines.append("👇 *Pilih menu tindakan:*")

    keyboard_buttons.append([
        InlineKeyboardButton("💾 Simpan Tiket & Pantau Live Score", callback_data="track_save_parlay"),
    ])
    keyboard_buttons.append([
        InlineKeyboardButton("💵 Atur Modal Bankroll", callback_data="menu_bankroll"),
        InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_main"),
    ])

    return "\n".join(lines), InlineKeyboardMarkup(keyboard_buttons)


# ---------------------------------------------------------------------------
# 3. Real-Time Schedule Formatter (Today / Tomorrow)
# ---------------------------------------------------------------------------

def format_live_schedule_view(
    schedule_list: list[dict],
    current_day: str = "today",
) -> tuple[str, InlineKeyboardMarkup]:
    """Format real-time schedule grouped by league with 1-click analysis buttons."""
    day_title = "HARI INI (LIVE)" if current_day == "today" else "BESOK (UPCOMING)"
    lines = [
        f"📅 *JADWAL PERTANDINGAN REAL-TIME: {day_title}* 📅",
        "🌐 _Data Live Terhubung ke soccervital.com_",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "Pilih pertandingan di bawah untuk langsung menganalisis pasaran SBOBET 1-klik:\n",
    ]

    keyboard: list[list[InlineKeyboardButton]] = []

    tab_row = [
        InlineKeyboardButton("▶️ [ Laga Hari Ini ]" if current_day == "today" else "📅 Laga Hari Ini", callback_data="sched_tab_today"),
        InlineKeyboardButton("▶️ [ Laga Besok ]" if current_day == "tomorrow" else "🔮 Laga Besok", callback_data="sched_tab_tomorrow"),
    ]
    keyboard.append(tab_row)

    # Group by league
    grouped: dict[str, list[dict]] = {}
    for m in schedule_list:
        l = m.get("league", "General League")
        if l not in grouped:
            grouped[l] = []
        grouped[l].append(m)

    total_matches = 0
    for league_name, matches in grouped.items():
        lines.append(f"🏆 *{league_name}*")
        for m in matches[:3]:  # up to 3 matches per league
            total_matches += 1
            pred = m.get("pred_score", "2:1")
            lines.append(
                f"• *{m['home']} vs {m['away']}* `(Prediksi Skor: {pred})`\n"
                f"   ⏰ `{m['time']}` | Tip: *{m.get('tip', '1')}* (Odds 1: `{m.get('odds_1', 1.85)}` | 2: `{m.get('odds_2', 2.10)}`)"
            )
            keyboard.append([
                InlineKeyboardButton(
                    f"🔍 Analisis: {m['home']} vs {m['away']}",
                    callback_data=f"sched_match_{m['id']}",
                )
            ])
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    keyboard.append([
        InlineKeyboardButton("⚡ Analisis Semua Laga Jadi 1 Parlay", callback_data=f"sched_parlay_{current_day}"),
    ])
    keyboard.append([InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_main")])

    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


# ---------------------------------------------------------------------------
# 4. Bet Tracker & Live Score Monitoring Dashboard Formatter
# ---------------------------------------------------------------------------

def format_tracker_dashboard(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Format personal bet tracker history, active live slips, and win rate stats."""
    stats = tracker.get_user_stats(user_id)
    active_slips = tracker.get_user_slips(user_id, limit=5, status="PENDING")
    active_slips += tracker.get_user_slips(user_id, limit=5, status="LIVE")

    profit_color = "🟢" if stats.net_profit > 0 else ("🔴" if stats.net_profit < 0 else "⚪")
    profit_sign = "+" if stats.net_profit > 0 else ""

    lines = [
        "📈 *DASHBOARD PERSONAL BET TRACKER & LIVE MONITOR* 📈",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🏆 *Win Rate Personal:* `{stats.win_rate_pct}%` {_progress_bar(stats.win_rate_pct, 10)}",
        f"📊 *Rekor:* `{stats.wins} Menang` | `{stats.losses} Kalah` | `{stats.voids} Void`",
        f"⏳ *Tiket Berjalan:* `{stats.pending} Tiket Aktif Dipantau`",
        f"💰 *Total Modal Terpasang:* `{_format_rupiah(stats.total_staked)}`",
        f"{profit_color} *Net Profit / Loss:* `{profit_sign}{_format_rupiah(stats.net_profit)}`",
        f"📈 *ROI:* `{profit_sign}{stats.roi_pct}%` | Streak: `{stats.current_streak}`",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    keyboard: list[list[InlineKeyboardButton]] = []

    if active_slips:
        lines.append("🛰️ *TIKET BERJALAN & STATUS SKOR LANGSUNG:*")
        for s in active_slips:
            status_badge = "🔴 LIVE" if s.status == "LIVE" else "⏳ PENDING"
            lines.append(
                f"• *[#{s.id}] {s.slip_title}* (`{status_badge}` @`{s.total_odds:.2f}`)\n"
                f"   💰 Pasang: `{_format_rupiah(s.stake_amount)}` | Potensi: `{_format_rupiah(s.potential_return)}`\n"
                f"   📡 Linimasa: _{s.live_status_summary}_\n"
            )
            keyboard.append([
                InlineKeyboardButton(f"✅ #{s.id} WIN", callback_data=f"settle_{s.id}_WIN"),
                InlineKeyboardButton(f"❌ #{s.id} LOSE", callback_data=f"settle_{s.id}_LOSE"),
                InlineKeyboardButton(f"🔄 #{s.id} VOID", callback_data=f"settle_{s.id}_VOID"),
            ])
    else:
        lines.append("ℹ️ *Belum ada tiket berjalan.* Setiap kali kamu menganalisis laga, klik `💾 Simpan Tiket` agar bot memantau skornya secara otomatis!")

    keyboard.append([
        InlineKeyboardButton("🔄 Refresh Skor Live", callback_data="menu_tracker"),
        InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_main"),
    ])

    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


# ---------------------------------------------------------------------------
# 5. Bankroll Calculator Formatter
# ---------------------------------------------------------------------------

def format_bankroll_view(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Format bankroll setup and quick-set buttons."""
    current = tracker.get_user_bankroll(user_id)
    u_safe = current * 0.02
    u_mod = current * 0.04
    u_agg = current * 0.06

    lines = [
        "💵 *KALKULATOR BANKROLL & STAKING RUPIAH* 💵",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"💼 *Modal Bankroll Aktif:* `{_format_rupiah(current)}`\n",
        "📐 *Panduan Alokasi Unit Pasang (Kelly Criterion):*",
        f"• 🟢 *Konservatif (1-2%):* `{_format_rupiah(u_safe)}` _(Minim resiko)_",
        f"• 🟡 *Moderat (3-4%):* `{_format_rupiah(u_mod)}` _(Rekomendasi default)_",
        f"• 🔴 *Agresif (5-6%):* `{_format_rupiah(u_agg)}` _(Khusus laga super +EV)_\n",
        "💡 *Pilih nominal cepat di bawah atau ketik manual*:",
        "Contoh: `/bankroll 2500000`",
    ]

    keyboard = [
        [
            InlineKeyboardButton("Rp 250.000", callback_data="set_bankroll_250000"),
            InlineKeyboardButton("Rp 500.000", callback_data="set_bankroll_500000"),
        ],
        [
            InlineKeyboardButton("Rp 1.000.000", callback_data="set_bankroll_1000000"),
            InlineKeyboardButton("Rp 2.500.000", callback_data="set_bankroll_2500000"),
        ],
        [
            InlineKeyboardButton("Rp 5.000.000", callback_data="set_bankroll_5000000"),
            InlineKeyboardButton("Rp 10.000.000", callback_data="set_bankroll_10000000"),
        ],
        [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_main")],
    ]
    return "\n".join(lines), InlineKeyboardMarkup(keyboard)
