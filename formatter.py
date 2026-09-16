"""
formatter.py — Rich Telegram Markdown Formatter & Interactive Inline Keyboard Builder.
Provides professional visual layouts, progress bars, Rupiah staking calculations,
and interactive navigation for Top Picks, Optimizer, Bet Tracker, Schedule, and Markets.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from models import (
    DeepMatchAnalysis,
    OptimizedParlayPackage,
    ParlayAnalysisReport,
    TopPickCategory,
    TopPickItem,
    TrackedBet,
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
# 1. Main Parlay Overview with Staking & Optimizer Buttons
# ---------------------------------------------------------------------------

def format_parlay_overview(
    report: ParlayAnalysisReport,
    user_id: int | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    """Format executive summary, mathematical outputs, and interactive actions."""
    bankroll = tracker.get_user_bankroll(user_id) if user_id else 1000000.0
    rec_stake_pct = report.recommended_kelly_stake
    rec_stake_rp = bankroll * rec_stake_pct
    pot_return_rp = rec_stake_rp * report.combined_odds
    net_profit_rp = pot_return_rp - rec_stake_rp

    ev_sign = "+" if report.overall_expected_value > 0 else ""
    ev_color = "🟢" if report.overall_expected_value > 0.05 else ("🟡" if report.overall_expected_value >= 0 else "🔴")

    lines: list[str] = [
        "🏆 *LAPORAN ANALISIS PARLAY PROFESIONAL* 🏆",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📊 *Jumlah Laga:* `{len(report.matches)} Pertandingan`",
        f"💰 *Total Odds Tiket:* `@{report.combined_odds:.2f}`",
        f"🎯 *True Win Probability:* `{report.combined_true_probability * 100:.1f}%`",
        f"{_progress_bar(report.combined_true_probability * 100, 10)}",
        f"⚖️ *Fair Odds (Bebas Komisi):* `@{report.combined_fair_odds:.2f}`",
        f"{ev_color} *Overall +EV (Nilai Keuntungan):* `{ev_sign}{report.overall_expected_value * 100:.1f}%`",
        f"🛡️ *Tingkat Resiko:* `{report.risk_tier}`",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "💵 *REKOMENDASI STAKING & MODAL RUPIAH:*",
        f"• 💼 *Total Bankroll Kamu:* `{_format_rupiah(bankroll)}`",
        f"• 💰 *Saran Pasang (Kelly):* `{_format_rupiah(rec_stake_rp)}` _({rec_stake_pct*100:.1f}% modal)_",
        f"• 🎯 *Estimasi Profit Bersih:* `+{_format_rupiah(net_profit_rp)}`",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    if report.core_anchor_leg:
        lines.append(f"⭐ *Core Anchor (Laga Paling Solid):* `{report.core_anchor_leg.clean_title()}`")
        lines.append("")

    lines.append(f"📝 *Executive Summary:*\n_{report.executive_summary}_")
    lines.append("")
    lines.append("📋 *PERFORMA SETIAP PERTANDINGAN:*")

    keyboard_buttons: list[list[InlineKeyboardButton]] = []

    for i, m in enumerate(report.matches, start=1):
        leg = m.leg
        ev_item_sign = "+" if m.expected_value > 0 else ""
        badge = "🟢" if m.expected_value > 0.05 else ("🟡" if m.expected_value >= 0 else "🔴")
        if m.is_trap_candidate:
            badge = "⚠️ TRAP"

        lines.append(
            f"{i}. *{leg.home} vs {leg.away}*\n"
            f"   • Pilihan: `{leg.pick}` @`{leg.odds:.2f}`\n"
            f"   • True Prob: `{m.true_probability * 100:.1f}%` | EV: `{badge} {ev_item_sign}{m.expected_value * 100:.1f}%`"
        )
        btn_text = f"{badge} Laga #{i}: {leg.home} vs {leg.away}"
        keyboard_buttons.append([InlineKeyboardButton(btn_text, callback_data=f"match_{i-1}")])

    lines.append("")
    lines.append("👇 *Pilih menu tindakan di bawah:*")

    # Action Buttons
    action_row = [
        InlineKeyboardButton("🛡️ Optimasi & Filter Trap", callback_data="opt_parlay"),
        InlineKeyboardButton("💾 Simpan ke Tracker", callback_data="track_save_parlay"),
    ]
    util_row = [
        InlineKeyboardButton("💵 Atur Modal (Bankroll)", callback_data="menu_bankroll"),
        InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_main"),
    ]
    keyboard_buttons.append(action_row)
    keyboard_buttons.append(util_row)

    return "\n".join(lines), InlineKeyboardMarkup(keyboard_buttons)


# ---------------------------------------------------------------------------
# 2. Single Match Deep Dive Formatter
# ---------------------------------------------------------------------------

def format_single_match_deep_dive(
    m: DeepMatchAnalysis,
    index: int,
    total: int,
    user_id: int | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    """Format in-depth Poisson, market odds, and tactical breakdown for single match."""
    bankroll = tracker.get_user_bankroll(user_id) if user_id else 1000000.0
    leg = m.leg
    p = m.poisson
    t = m.tactical
    single_stake_rp = bankroll * m.kelly_fractional_stake
    single_profit_rp = (single_stake_rp * leg.odds) - single_stake_rp

    ev_sign = "+" if m.expected_value > 0 else ""
    ev_badge = "🟢 SANGAT BAGUS (+EV)" if m.expected_value > 0.05 else ("🟡 NETRAL" if m.expected_value >= 0 else "🔴 OVERVALUED (-EV)")

    lines = [
        f"🔍 *DETAIL ANALISIS LAGA #{index + 1}/{total}* 🔍",
        f"⚽ *{leg.home} vs {leg.away}*",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📌 *Pilihan Taruhan:* `{leg.pick}` @`{leg.odds:.2f}`",
        f"🎯 *True Probability:* `{m.true_probability * 100:.1f}%` {_progress_bar(m.true_probability * 100, 8)}",
        f"⚖️ *Fair Odds Bandar:* `@{m.fair_odds:.2f}`",
        f"📊 *Status Value (+EV):* `{ev_badge} ({ev_sign}{m.expected_value * 100:.1f}%)`",
        f"💰 *Saran Pasang Single:* `{_format_rupiah(single_stake_rp)}` _(Estimasi Cuan: +{_format_rupiah(single_profit_rp)})_",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "📐 *MODEL STATISTIK POISSON & xG:*",
        f"• Proyeksi xG: `{leg.home} ({p.lambda_home:.2f})` vs `({p.lambda_away:.2f}) {leg.away}`",
        f"• Probabilitas 1X2: `{int(p.prob_home_win*100)}% Menang` | `{int(p.prob_draw*100)}% Seri` | `{int(p.prob_away_win*100)}% Kalah`",
        f"• Peluang Over 2.5: `{int(p.prob_over_25*100)}%` | Under 2.5: `{int(p.prob_under_25*100)}%`",
        f"• Peluang BTTS (Gol Kedua Tim): `{int(p.prob_btts_yes*100)}%`",
    ]

    if p.top_exact_scores:
        scores_str = ", ".join(f"`{s[0]}` ({int(s[1]*100)}%)" for s in p.top_exact_scores[:3])
        lines.append(f"• Skor Paling Mungkin: {scores_str}")

    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🧠 *AI TACTICAL & BETTING INSIGHT:*",
        f"• 📋 *Ringkasan:* {t.summary}",
        f"• ⚔️ *Benturan Taktik:* {t.tactical_clash}",
        f"• ⚠️ *Titik Lemah:* {t.key_vulnerabilities}",
        f"• 🚨 *Trap Warning:* {t.trap_warning}",
        f"• 🔮 *Skenario Laga:* {t.scenario_prediction}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ])

    if m.alternative_safe_pick or m.alternative_high_ev_pick:
        lines.append("💡 *ALTERNATIF PASARAN LAIN:*")
        if m.alternative_safe_pick:
            lines.append(f"• 🛡️ *Opsi Lebih Aman (Floor Tinggi):* `{m.alternative_safe_pick}`")
        if m.alternative_high_ev_pick:
            lines.append(f"• 💎 *Opsi Cuan Maksimal (+EV Tinggi):* `{m.alternative_high_ev_pick}`")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
def format_top_picks_view(picks: list[TopPickItem]) -> tuple[str, InlineKeyboardMarkup]:
    """Format daily factual AI top picks from SoccerVital live feed."""
    lines: list[str] = [
        "🔥 *AI TOP PICKS OF THE DAY (FAKTUAL & REAL-TIME)* 🔥",
        "🌐 _Live Intelligence Feed dari SoccerVital.com & Model Poisson xG_",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "Rekomendasi pertandingan riil hari ini dengan probabilitas menang tinggi, "
        "nilai (+EV), dan proyeksi skor akurat:\n",
    ]

    keyboard_buttons: list[list[InlineKeyboardButton]] = []

    for idx, p in enumerate(picks, start=1):
        badge = "🛡️" if "Safe" in p.category.value else ("💎" if "+EV" in p.category.value else ("⚽" if "Goals" in p.category.value else "🚩"))
        lines.extend([
            f"{badge} *#{idx}. {p.match_title}*",
            f"   • 🏆 Liga: `{p.league}` | ⏰ Kickoff: `{p.kickoff}`",
            f"   • 🎯 Pilihan: *{p.pick}* @`{p.odds:.2f}`",
            f"   • 📊 Win Prob: `{p.win_probability * 100:.1f}%` {_progress_bar(p.win_probability * 100, 6)}",
            f"   • 💎 Nilai +EV: `+{p.expected_value * 100:.1f}%` | Keyakinan: `{p.confidence_pct}%`",
            f"   • 💡 Alasan: _{p.tactical_rationale}_",
            f"   • 📈 Data Kunci: _{p.key_stat}_\n",
        ])

        btn_text = f"🔍 Analisis #{idx}: {p.match_title} ({p.pick})"
        keyboard_buttons.append([InlineKeyboardButton(btn_text, callback_data=f"top_analyze_{p.id}")])

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 *Pilih tombol di bawah untuk analisis instan atau pasang kombo:*")

    keyboard_buttons.append([
        InlineKeyboardButton("⚡ Gabungkan Semua Top Picks Jadi 1 Parlay", callback_data="top_parlay_all"),
    ])
    keyboard_buttons.append([
        InlineKeyboardButton("🔄 Refresh Data Live", callback_data="menu_top_picks"),
        InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_main"),
    ])

    return "\n".join(lines), InlineKeyboardMarkup(keyboard_buttons)
def format_optimized_parlay_view(
    opt: OptimizedParlayPackage,
    user_id: int | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    """Format parlay optimizer dividing slip into Safe Package, Value Package, and Traps."""
    bankroll = tracker.get_user_bankroll(user_id) if user_id else 1000000.0

    lines: list[str] = [
        "🛡️ *PARLAY SLIP OPTIMIZER & TRAP ELIMINATOR* 🛡️",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "AI telah membedah seluruh laga tiket kamu dan menyusun paket rekomendasi optimal:\n",
    ]

    # 1. Conservative Safe Package
    safe_stake = bankroll * opt.safe_kelly_stake
    safe_profit = (safe_stake * opt.safe_odds) - safe_stake
    lines.extend([
        "🟢 *1. PAKET KONSERVATIF (LOW RISK ANCHOR)*",
        f"• Jumlah Laga: `{len(opt.safe_legs)} Laga Terpilih Paling Stabil`",
        f"• Total Odds: `@{opt.safe_odds:.2f}`",
        f"• Peluang Tembus: `{opt.safe_win_prob * 100:.1f}%` {_progress_bar(opt.safe_win_prob * 100, 6)}",
        f"• Saran Pasang: `{_format_rupiah(safe_stake)}` _(Estimasi Profit: +{_format_rupiah(safe_profit)})_",
        "• *Daftar Laga:*",
    ])
    for s in opt.safe_legs:
        lines.append(f"   ✓ `{s.leg.clean_title()}` — *{s.leg.pick}* @`{s.leg.odds:.2f}` (Win Prob: {s.true_probability*100:.0f}%)")
    lines.append("")

    # 2. Maximum Value Sharp Package
    val_stake = bankroll * opt.value_kelly_stake
    val_profit = (val_stake * opt.value_odds) - val_stake
    lines.extend([
        "💎 *2. PAKET CUAN MAKSIMAL (HIGH +EV VALUE)*",
        f"• Jumlah Laga: `{len(opt.value_legs)} Laga Bernilai Tinggi`",
        f"• Total Odds: `@{opt.value_odds:.2f}`",
        f"• Overall +EV: `+{opt.value_expected_value * 100:.1f}%` (Harga Bandar Terlalu Murah)",
        f"• Saran Pasang: `{_format_rupiah(val_stake)}` _(Estimasi Profit: +{_format_rupiah(val_profit)})_",
        "• *Daftar Laga:*",
    ])
    for v in opt.value_legs:
        lines.append(f"   ✓ `{v.leg.clean_title()}` — *{v.leg.pick}* @`{v.leg.odds:.2f}` (+EV: {v.expected_value*100:+.1f}%)")
    lines.append("")

    # 3. Traps / Filtered Out
    if opt.trapped_legs:
        lines.extend([
            "⚠️ *3. LAGU TERINDIKASI JEBAKAN BANDAR (DISARANKAN DIBUANG)*",
        ])
        for t_leg, reasons in opt.trapped_legs:
            r_str = ", ".join(reasons)
            lines.append(f"   ❌ `{t_leg.leg.clean_title()}` — *{t_leg.leg.pick}* @`{t_leg.leg.odds:.2f}`")
            lines.append(f"      _Alasan Bahaya: {r_str}_")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("👇 *Pilih paket yang ingin kamu eksekusi:*")

    keyboard = [
        [InlineKeyboardButton("🟢 Analisis Paket Aman (2-3 Laga)", callback_data="opt_run_safe")],
        [InlineKeyboardButton("💎 Analisis Paket +EV Cuan Maksimal", callback_data="opt_run_value")],
        [InlineKeyboardButton("🔙 Kembali ke Tiket Asli", callback_data="back_summary")],
    ]
    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


# ---------------------------------------------------------------------------
# 5. Bankroll Calculator Formatter
# ---------------------------------------------------------------------------

def format_bankroll_calculator_view(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Format bankroll setup and interactive staking tiers."""
    current_bankroll = tracker.get_user_bankroll(user_id)
    conservative_unit = current_bankroll * 0.02
    balanced_unit = current_bankroll * 0.04
    aggressive_unit = current_bankroll * 0.07

    lines = [
        "💵 *KALKULATOR BANKROLL & MANAJEMEN MODAL* 💵",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"💼 *Modal Aktif Kamu:* `{_format_rupiah(current_bankroll)}`\n",
        "📐 *Panduan Alokasi Unit Pasang (Kelly Standard):*",
        f"• 🟢 *Konservatif (1-2%):* `{_format_rupiah(conservative_unit)}` _(Sangat aman, minim resiko)_",
        f"• 🟡 *Moderat (3-4%):* `{_format_rupiah(balanced_unit)}` _(Rekomendasi default)_",
        f"• 🔴 *Agresif (5-7%):* `{_format_rupiah(aggressive_unit)}` _(Khusus laga +EV sangat tinggi)_\n",
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


# ---------------------------------------------------------------------------
# 6. Bet Tracker & Performance Analytics Formatter
# ---------------------------------------------------------------------------

def format_tracker_dashboard(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Format personal bet tracker history, win rate %, and settled cards."""
    stats = tracker.get_user_stats(user_id)
    pending_bets = tracker.get_user_bets(user_id, limit=5, status="PENDING")
    recent_history = tracker.get_user_bets(user_id, limit=5)

    profit_color = "🟢" if stats.net_profit > 0 else ("🔴" if stats.net_profit < 0 else "⚪")
    profit_sign = "+" if stats.net_profit > 0 else ""

    lines = [
        "📈 *DASHBOARD PERSONAL BET TRACKER & WIN-RATE* 📈",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🏆 *Win Rate:* `{stats.win_rate_pct}%` {_progress_bar(stats.win_rate_pct, 10)}",
        f"📊 *Rekor:* `{stats.wins} Menang` | `{stats.losses} Kalah` | `{stats.voids} Void`",
        f"⏳ *Tiket Berjalan:* `{stats.pending} Tiket Menunggu Hasil`",
        f"💰 *Total Modal Dipasang:* `{_format_rupiah(stats.total_staked)}`",
        f"{profit_color} *Net Profit / Loss:* `{profit_sign}{_format_rupiah(stats.net_profit)}`",
        f"📈 *ROI (Return on Investment):* `{profit_sign}{stats.roi_pct}%`",
        f"🔥 *Status Streak:* `{stats.current_streak}`",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    keyboard: list[list[InlineKeyboardButton]] = []

    if pending_bets:
        lines.append("⏳ *TIKET BERJALAN (KLIK UNTUK SELESAIKAN HASIL):*")
        for b in pending_bets:
            lines.append(
                f"• *[#{b.id}] {b.ticket_title}* @`{b.odds:.2f}`\n"
                f"   Pasang: `{_format_rupiah(b.stake_amount)}` | Potensi: `{_format_rupiah(b.potential_return)}`\n"
                f"   _{b.legs_summary}_\n"
            )
            keyboard.append([
                InlineKeyboardButton(f"✅ #{b.id} WIN", callback_data=f"settle_{b.id}_WIN"),
                InlineKeyboardButton(f"❌ #{b.id} LOSE", callback_data=f"settle_{b.id}_LOSE"),
                InlineKeyboardButton(f"🔄 #{b.id} VOID", callback_data=f"settle_{b.id}_VOID"),
            ])
    else:
        lines.append("ℹ️ *Belum ada tiket berjalan.* Setiap kali kamu menganalisis parlay, klik tombol `💾 Simpan ke Tracker` agar tercatat otomatis!")

def format_schedule_view(
    schedule_dict: dict[str, list[dict]],
    current_day: str = "today",
) -> tuple[str, InlineKeyboardMarkup]:
    """Format real-time match schedule across leagues for TODAY or TOMORROW."""
    day_title = "HARI INI (LIVE)" if current_day == "today" else "BESOK (UPCOMING)"
    lines = [
        f"📅 *JADWAL PERTANDINGAN REAL-TIME: {day_title}* 📅",
        "🌐 _Live Fixture Feed dari soccervital.com_",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "Pilih laga di bawah untuk langsung menganalisis taktik & statistik Poisson 1-klik:\n",
    ]

    keyboard: list[list[InlineKeyboardButton]] = []

    # Day Toggle Tabs
    tab_row = [
        InlineKeyboardButton("▶️ [ Laga Hari Ini ]" if current_day == "today" else "📅 Laga Hari Ini", callback_data="sched_day_today"),
        InlineKeyboardButton("▶️ [ Laga Besok ]" if current_day == "tomorrow" else "🔮 Laga Besok", callback_data="sched_day_tomorrow"),
    ]
    keyboard.append(tab_row)

    total_matches_shown = 0
    for league_name, matches in schedule_dict.items():
        if not matches:
            continue
        lines.append(f"🏆 *{league_name}*")
        for m in matches[:4]:  # show up to 4 top matches per league
            total_matches_shown += 1
            badge = m.get("hot_badge", "⚽ Live Match")
            lines.append(
                f"• *{m['home']} vs {m['away']}* `{badge}`\n"
                f"   ⏰ `{m['time']}` | Tip Pasar: *{m.get('default_pick', 'Win')}* @`{m.get('odds', 1.85):.2f}`"
            )
            keyboard.append([
                InlineKeyboardButton(
                    f"🔍 #{total_matches_shown}: {m['home']} vs {m['away']}",
                    callback_data=f"sched_analyze_{m['id']}",
                )
            ])
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    keyboard.append([
        InlineKeyboardButton("⚡ Gabungkan Jadi 1 Parlay Otomatis", callback_data=f"sched_parlay_{current_day}"),
    ])
    keyboard.append([InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_main")])

    return "\n".join(lines), InlineKeyboardMarkup(keyboard)
# ---------------------------------------------------------------------------
# 8. Specific Market Filter Formatter
# ---------------------------------------------------------------------------

def format_market_filter_view() -> tuple[str, InlineKeyboardMarkup]:
    """Format specialized market filter dashboard."""
    lines = [
        "🎯 *MODE ANALISIS SPESIFIK PASARAN (MARKET FILTER)* 🎯",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "Pilih tipe pasaran fokus yang ingin kamu eksplorasi:\n",
        "• ⚽ *Over / Under 2.5 Total Gol:* Mengidentifikasi laga potensi banjir gol vs laga defensif alot.",
        "• 🤝 *Both Teams to Score (BTTS / GG):* Mencari duel tim agresif dengan kelemahan defensif di kedua kubu.",
        "• 🚩 *Asian Handicap (HDP / Voor):* Menganalisis ketahanan voor dan peluang pesta gol favorit.",
        "• 🏆 *1X2 Match Winner:* Mencari keunggulan probabilitas murni tim pemenang.",
    ]

    keyboard = [
        [
            InlineKeyboardButton("⚽ Filter: Over / Under Gol", callback_data="market_filter_ou"),
            InlineKeyboardButton("🤝 Filter: BTTS (GG)", callback_data="market_filter_btts"),
        ],
        [
            InlineKeyboardButton("🚩 Filter: Asian Handicap", callback_data="market_filter_hdp"),
            InlineKeyboardButton("🏆 Filter: 1X2 Match Winner", callback_data="market_filter_1x2"),
        ],
        [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_main")],
    ]
    return "\n".join(lines), InlineKeyboardMarkup(keyboard)
