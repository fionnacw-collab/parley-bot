"""
formatter.py — Clean, Simplified Telegram Formatter for SBOBET Match & Parlay Analysis.
Designed for maximum readability, clean structure, and straightforward betting insights.
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


def _format_rupiah(amount: float) -> str:
    """Format float into standard Indonesian Rupiah format (Rp X.XXX.XXX)."""
    val = int(round(amount))
    return f"Rp {val:,}".replace(",", ".")


# ---------------------------------------------------------------------------
# 1. Single Match Analysis Formatter (Clean & Sederhana)
# ---------------------------------------------------------------------------

def format_single_match_analysis(
    analysis: DeepMatchAnalysis,
    user_id: int | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    """Format clean, simplified SBOBET analysis for a single fixture."""
    bankroll = tracker.get_user_bankroll(user_id) if user_id else 1000000.0
    m = analysis.match
    p = analysis.poisson
    best = analysis.best_sbobet_pick

    stake_rp = max(10000.0, bankroll * analysis.recommended_stake_pct)
    profit_rp = (stake_rp * best.projected_odds) - stake_rp

    top_score = analysis.predicted_score or (p.top_exact_scores[0][0] if p.top_exact_scores else "2 - 1")

    lines = [
        f"⚽ *{m.home.upper()} vs {m.away.upper()}*",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🎯 *Prediksi Skor:* `{top_score}`",
        "",
        "⭐ *REKOMENDASI UTAMA SBOBET:*",
        f"👉 *{best.selection}* @`{best.projected_odds:.2f}`",
        f"• Pasaran: `{best.sbobet_line_display}`",
        f"• Peluang Menang: `{int(best.win_probability * 100)}%`",
        f"• Alasan: _{best.reasoning}_",
        "",
        "📋 *PILIHAN PASARAN LAIN:*",
    ]

    for market in analysis.all_sbobet_markets:
        if market.market_type != best.market_type:
            lines.append(f"• {market.market_type.value}: *{market.selection}* @`{market.projected_odds:.2f}`")

    lines.extend([
        "",
        "🧠 *Catatan Taktis:*",
        f"{analysis.tactical_summary}",
    ])

    if analysis.is_trap:
        lines.append(f"⚠️ *Perhatian:* _{analysis.trap_warning}_")

    lines.extend([
        "",
        f"💵 *Rekomendasi Pasang (Modal {_format_rupiah(bankroll)}):*",
        f"• Pasang: `{_format_rupiah(stake_rp)}` $\\rightarrow$ *Potensi Cuan: `+{_format_rupiah(profit_rp)}`*",
    ])

    keyboard = [
        [InlineKeyboardButton("💾 Simpan ke Tracker & Pantau Skor", callback_data="track_save_single_0")],
        [
            InlineKeyboardButton("💵 Atur Modal Bankroll", callback_data="menu_bankroll"),
            InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_main"),
        ],
    ]

    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


# ---------------------------------------------------------------------------
# 2. Multi-Match Parlay Formatter (Clean, Top Picks, & Simple Packages)
# ---------------------------------------------------------------------------

def format_parlay_analysis(
    report: ParlayAnalysisReport,
    user_id: int | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    """Format simplified, crystal clear multi-match parlay overview."""
    bankroll = tracker.get_user_bankroll(user_id) if user_id else 1000000.0
    total_matches = len(report.matches)

    # Sort matches by best analytical quality
    sorted_matches = sorted(
        report.matches,
        key=lambda m: (m.best_sbobet_pick.expected_value * 0.6) + (m.best_sbobet_pick.win_probability * 0.4),
        reverse=True,
    )

    top_count = min(5, total_matches)
    top_picks = sorted_matches[:top_count]

    lines = [
        f"🏆 *HASIL ANALISIS SBOBET ({total_matches} PERTANDINGAN)* 🏆",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🔥 *TOP {top_count} REKOMENDASI TERBAIK HARI INI:*\n",
    ]

    for idx, m in enumerate(top_picks, start=1):
        best = m.best_sbobet_pick
        score = m.predicted_score or (m.poisson.top_exact_scores[0][0] if m.poisson.top_exact_scores else "2 - 1")
        lines.extend([
            f"*{idx}. {m.match.clean_title()}*",
            f"   👉 *{best.selection}* @`{best.projected_odds:.2f}` _({best.sbobet_line_display})_",
            f"   🎯 Prediksi Skor: `{score}` | Peluang: `{int(best.win_probability * 100)}%`\n",
        ])

    # Construct Clean Parlay Packages
    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "💰 *SARAN PAKET MIX PARLAY:*",
        "",
    ])

    # 1. Conservative Safe Package (Top 3-4 Highest Probability)
    safe_count = min(3, total_matches)
    safe_matches = sorted(report.matches, key=lambda m: m.best_sbobet_pick.win_probability, reverse=True)[:safe_count]
    safe_odds = 1.0
    safe_prob = 1.0
    for s in safe_matches:
        safe_odds *= s.best_sbobet_pick.projected_odds
        safe_prob *= s.best_sbobet_pick.win_probability

    safe_stake = max(10000.0, bankroll * 0.035)
    safe_profit = (safe_stake * safe_odds) - safe_stake

    lines.extend([
        f"🟢 *1. Paket Aman ({safe_count}-Laga Paling Stabil)*",
        f"• Total Odds: `@{safe_odds:.2f}` | Peluang Tembus: `{int(safe_prob * 100)}%`",
        f"• Saran Pasang: `{_format_rupiah(safe_stake)}` $\\rightarrow$ *Potensi Cuan: `+{_format_rupiah(safe_profit)}`*",
        "• *Pilihan Laga:* " + ", ".join(f"`{s.match.home} ({s.best_sbobet_pick.selection})`" for s in safe_matches),
        "",
    ])

    # 2. Maximum Value Sharp Package (Top Picks Combined)
    if total_matches >= 4:
        val_odds = 1.0
        for v in top_picks:
            val_odds *= v.best_sbobet_pick.projected_odds

        val_stake = max(10000.0, bankroll * 0.015)
        val_profit = (val_stake * val_odds) - val_stake

        lines.extend([
            f"💎 *2. Paket Cuan ({top_count}-Laga Top Picks)*",
            f"• Total Odds: `@{val_odds:.2f}`",
            f"• Saran Pasang: `{_format_rupiah(val_stake)}` $\\rightarrow$ *Potensi Cuan: `+{_format_rupiah(val_profit)}`*",
            "",
        ])

    # If more than 5 matches, show clean 1-line list for all matches
    if total_matches > 5:
        lines.extend([
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"📋 *RINGKASAN LENGKAP {total_matches} LAGA:*",
        ])
        for i, m in enumerate(report.matches, start=1):
            best = m.best_sbobet_pick
            score = m.predicted_score or (m.poisson.top_exact_scores[0][0] if m.poisson.top_exact_scores else "2 - 1")
            lines.append(
                f"`{i:02d}.` *{m.match.home} vs {m.match.away}* $\\rightarrow$ `{best.selection}` @`{best.projected_odds:.2f}` | Skor: `{score}`"
            )
        lines.append("")

    keyboard_buttons: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton("💾 Simpan Tiket & Pantau Skor Live", callback_data="track_save_parlay")],
        [
            InlineKeyboardButton("💵 Atur Modal Bankroll", callback_data="menu_bankroll"),
            InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_main"),
        ],
    ]

    return "\n".join(lines), InlineKeyboardMarkup(keyboard_buttons)


# ---------------------------------------------------------------------------
# 3. Real-Time Schedule Formatter (Today / Tomorrow)
# ---------------------------------------------------------------------------

def format_live_schedule_view(
    schedule_list: list[dict],
    current_day: str = "today",
) -> tuple[str, InlineKeyboardMarkup]:
    """Format clean real-time schedule grouped by league with 1-click analysis buttons."""
    day_title = "HARI INI (LIVE)" if current_day == "today" else "BESOK (UPCOMING)"
    lines = [
        f"📅 *JADWAL PERTANDINGAN: {day_title}* 📅",
        "🌐 _Data Live soccervital.com_",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "Klik tombol pertandingan di bawah untuk langsung analisis:\n",
    ]

    keyboard: list[list[InlineKeyboardButton]] = []

    tab_row = [
        InlineKeyboardButton("▶️ [ Hari Ini ]" if current_day == "today" else "📅 Hari Ini", callback_data="sched_tab_today"),
        InlineKeyboardButton("▶️ [ Besok ]" if current_day == "tomorrow" else "🔮 Besok", callback_data="sched_tab_tomorrow"),
    ]
    keyboard.append(tab_row)

    grouped: dict[str, list[dict]] = {}
    for m in schedule_list:
        l = m.get("league", "General League")
        if l not in grouped:
            grouped[l] = []
        grouped[l].append(m)

    total_matches = 0
    for league_name, matches in grouped.items():
        lines.append(f"🏆 *{league_name}*")
        for m in matches[:3]:
            total_matches += 1
            pred = m.get("pred_score", "2:1")
            lines.append(f"• *{m['home']} vs {m['away']}* `(Prediksi Skor: {pred})`")
            keyboard.append([
                InlineKeyboardButton(
                    f"🔍 Analisis: {m['home']} vs {m['away']}",
                    callback_data=f"sched_match_{m['id']}",
                )
            ])
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    keyboard.append([
        InlineKeyboardButton("⚡ Analisis Semua Jadi 1 Parlay", callback_data=f"sched_parlay_{current_day}"),
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
        "📈 *BET TRACKER & PEMANTAU SKOR LIVE* 📈",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🏆 *Win Rate:* `{stats.win_rate_pct}%`",
        f"📊 *Rekor:* `{stats.wins} Menang` | `{stats.losses} Kalah` | `{stats.voids} Void`",
        f"⏳ *Tiket Aktif:* `{stats.pending} Tiket Sedang Dipantau`",
        f"💰 *Total Modal Terpasang:* `{_format_rupiah(stats.total_staked)}`",
        f"{profit_color} *Net Profit / Loss:* `{profit_sign}{_format_rupiah(stats.net_profit)}`",
        f"📈 *ROI:* `{profit_sign}{stats.roi_pct}%` | Streak: `{stats.current_streak}`",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    keyboard: list[list[InlineKeyboardButton]] = []

    if active_slips:
        lines.append("🛰️ *TIKET YANG SEDANG BERJALAN:*")
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
        lines.append("ℹ️ *Belum ada tiket berjalan.* Setelah analisis, klik `💾 Simpan Tiket` agar bot memantau skornya otomatis!")

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
        "📐 *Panduan Alokasi Pasang (Kelly Criterion):*",
        f"• 🟢 *Konservatif (1-2%):* `{_format_rupiah(u_safe)}` _(Minim resiko)_",
        f"• 🟡 *Moderat (3-4%):* `{_format_rupiah(u_mod)}` _(Rekomendasi default)_",
        f"• 🔴 *Agresif (5-6%):* `{_format_rupiah(u_agg)}` _(Khusus laga bernilai tinggi)_\n",
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
