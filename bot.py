"""
bot.py — Deep Football & Parlay Analysis Telegram Bot with Full Suite of Features:
- Google Gemini & OpenAI Vision for Multi-Page PDF & Screenshot Extraction
- 🔥 AI Top Picks of the Day (Categorized & Verified Value Edges)
- 🛡️ Parlay Slip Optimizer & False Favorite Trap Eliminator
- 💵 Bankroll & Rupiah Staking Calculator (Kelly Criterion)
- 📅 Marquee Match Schedule with 1-Click Instant Analysis
- 📈 Personal Bet Tracker & Win-Rate Analytics (SQLite Database)
- 🎯 Specialized Market Filters (Over/Under, BTTS, Handicap, 1X2)
- Interactive Inline Keyboard & Persistent Reply Keyboard System
- 24/7 Cloud Health Check HTTP Server
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import sys
import time

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import settings
from models import Leg, MarketCategory, ParlayAnalysisReport
from parser import parse_legs
from vision import extract_legs_from_image, extract_legs_from_pdf
from analyzer_engine import analyze_parlay
from optimizer import optimize_parlay
import top_picks
import schedule
import tracker
from formatter import (
    _format_rupiah,
    format_bankroll_calculator_view,
    format_market_filter_view,
    format_optimized_parlay_view,
    format_parlay_overview,
    format_schedule_view,
    format_single_match_deep_dive,
    format_top_picks_view,
    format_tracker_dashboard,
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("ParleyBot")

# In-memory storage for user analysis sessions: chat_id -> ParlayAnalysisReport
_ACTIVE_REPORTS: dict[int, ParlayAnalysisReport] = {}

# ---------------------------------------------------------------------------
# Persistent Bottom Reply Keyboard
# ---------------------------------------------------------------------------
MAIN_REPLY_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🔥 AI Top Picks Hari Ini"), KeyboardButton("📅 Jadwal & Top Match")],
        [KeyboardButton("🛡️ Optimasi Parlay"), KeyboardButton("📈 Bet Tracker & Win Rate")],
        [KeyboardButton("💵 Atur Modal (Bankroll)"), KeyboardButton("🎯 Filter Pasaran")],
        [KeyboardButton("⚽ Contoh Parlay (Demo)"), KeyboardButton("📄 Cara Kirim PDF / Foto")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for rich interactive dashboard navigation."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔥 AI Top Picks of the Day", callback_data="menu_top_picks")],
            [InlineKeyboardButton("📅 Jadwal Laga & 1-Klik Analisis", callback_data="menu_schedule")],
            [
                InlineKeyboardButton("🛡️ Optimasi Parlay", callback_data="opt_parlay"),
                InlineKeyboardButton("📈 Bet Tracker", callback_data="menu_tracker"),
            ],
            [
                InlineKeyboardButton("💵 Atur Modal Bankroll", callback_data="menu_bankroll"),
                InlineKeyboardButton("🎯 Filter Pasaran", callback_data="menu_market_filter"),
            ],
            [
                InlineKeyboardButton("⚽ Contoh Parlay (Demo)", callback_data="menu_demo"),
                InlineKeyboardButton("📄 Panduan Upload PDF", callback_data="menu_pdf_guide"),
            ],
            [
                InlineKeyboardButton("📊 Status Server & AI", callback_data="menu_status"),
                InlineKeyboardButton("📖 Panduan Lengkap", callback_data="menu_help"),
            ],
        ]
    )


# ---------------------------------------------------------------------------
# Telegram Reply Helpers
# ---------------------------------------------------------------------------

async def safe_reply(
    update: Update,
    text: str,
    reply_markup=None,
    parse_mode: str | None = "Markdown",
):
    """Send reply with Markdown, falling back to plain text if syntax fails."""
    target = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if not target:
        return

    try:
        if update.callback_query:
            await update.callback_query.message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
        else:
            await target.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
    except BadRequest as e:
        if "can't parse entities" in str(e).lower() and parse_mode:
            logger.warning("Markdown parse error, falling back to plain text")
            if update.callback_query:
                await update.callback_query.message.reply_text(text, reply_markup=reply_markup, parse_mode=None)
            else:
                await target.reply_text(text, reply_markup=reply_markup, parse_mode=None)
        else:
            raise e


# ---------------------------------------------------------------------------
# Command Handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command with rich dashboard menu."""
    text = (
        "🏆 *SELAMAT DATANG DI DEEP FOOTBALL & PARLAY ANALYZER* 🏆\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Platform analisis taruhan & tiket parlay cerdas bertenaga **Google Gemini AI & Pemodelan Statistik Poisson xG**.\n\n"
        "✨ *Fitur Unggulan Tersedia:*\n"
        "• 🔥 *AI Top Picks:* Rekomendasi laga harian paling bernilai (+EV).\n"
        "• 🛡️ *Parlay Optimizer:* Membagi tiket jadi paket aman & membuang jebakan bandar.\n"
        "• 💵 *Bankroll Calculator:* Rekomendasi nominal pasang Rupiah (Kelly Formula).\n"
        "• 📅 *Top Match Schedule:* Jadwal laga akbar dengan analisis 1-klik.\n"
        "• 📈 *Personal Bet Tracker:* Catat tiket & pantau grafik Win-Rate kamu.\n"
        "• 📄 *PDF Multi-Laga:* Kirim 1 file PDF berisi semua screenshot pertandingan!\n\n"
        "Gunakan menu tombol di bawah untuk langsung mulai 👇"
    )
    if update.message:
        await update.message.reply_text(
            text,
            reply_markup=MAIN_REPLY_KEYBOARD,
            parse_mode="Markdown",
        )
        await update.message.reply_text(
            "📋 *DASHBOARD MENU FITUR:*",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="Markdown",
        )
    else:
        await safe_reply(update, text, reply_markup=get_main_menu_keyboard())


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /menu command displaying the interactive dashboard."""
    text = (
        "📋 *DASHBOARD MENU UTAMA*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Pilih fitur yang ingin kamu gunakan:"
    )
    await safe_reply(update, text, reply_markup=get_main_menu_keyboard())


async def cmd_top_picks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /toppicks command."""
    picks = top_picks.get_daily_top_picks()
    text, markup = format_top_picks_view(picks)
    await safe_reply(update, text, reply_markup=markup)


async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /schedule command."""
    sched_data = schedule.get_marquee_schedule()
    text, markup = format_schedule_view(sched_data)
    await safe_reply(update, text, reply_markup=markup)


async def cmd_tracker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /tracker command."""
    chat_id = update.effective_chat.id
    text, markup = format_tracker_dashboard(chat_id)
    await safe_reply(update, text, reply_markup=markup)


async def cmd_bankroll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /bankroll command (view or set custom amount)."""
    chat_id = update.effective_chat.id
    args = context.args if context else []
    if args:
        try:
            val_str = args[0].replace(".", "").replace(",", "").replace("Rp", "").replace("rp", "")
            amount = float(val_str)
            saved = tracker.set_user_bankroll(chat_id, amount)
            await safe_reply(
                update,
                f"✅ *Bankroll berhasil diperbarui menjadi:* `{_format_rupiah(saved)}`\n"
                "Seluruh kalkulasi staking Kelly di tiket parlay akan otomatis disesuaikan.",
                reply_markup=get_main_menu_keyboard(),
            )
            return
        except Exception:
            pass

    text, markup = format_bankroll_calculator_view(chat_id)
    await safe_reply(update, text, reply_markup=markup)


async def cmd_optimize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /optimize command for active report."""
    chat_id = update.effective_chat.id
    report = _ACTIVE_REPORTS.get(chat_id)
    if not report:
        await safe_reply(
            update,
            "⚠️ Belum ada tiket parlay yang aktif untuk dioptimasi.\n"
            "Silakan kirim file PDF, foto slip, atau ketik daftar pertandingan terlebih dahulu.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    opt = optimize_parlay(report)
    text, markup = format_optimized_parlay_view(opt, chat_id)
    await safe_reply(update, text, reply_markup=markup)


async def cmd_markets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /markets command."""
    text, markup = format_market_filter_view()
    await safe_reply(update, text, reply_markup=markup)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command with detailed manual."""
    text = (
        "📖 *PANDUAN LENGKAP PENGGUNAAN BOT*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 *1. Cara Kirim Data Pertandingan:*\n"
        "• *File PDF (Paling Disarankan):* Kumpulkan semua screenshot pertandingan jadi 1 file PDF, lalu kirim ke bot. Bot membaca seluruh halaman otomatis via Gemini Vision.\n"
        "• *Foto Screenshot:* Kirim foto slip taruhan langsung (SBOBET, Bet365, dll).\n"
        "• *Teks Manual:* `Tim A vs Tim B - Pilihan @Odds`\n"
        "  Contoh: `Arsenal vs Chelsea - Over 2.5 @1.85`\n\n"
        "📌 *2. Arti Istilah & Metrik Analisis:*\n"
        "• *+EV (Expected Value):* Keuntungan matematis jangka panjang. Nilai positif (+EV) artinya odds bandar terlalu murah dibanding peluang aslinya.\n"
        "• *Poisson xG:* Simulasi distribusi gol ekspektasi berdasarkan form dan ketajaman kedua tim.\n"
        "• *Kelly Staking:* Rekomendasi nominal taruhan maksimal agar aman dari resiko drawdown/bangkrut.\n"
        "• *Core Anchor:* Laga paling solid yang sangat direkomendasikan menjadi fondasi parlay kamu.\n"
        "• *Trap Alert:* Laga favorit publik yang memiliki indikasi perangkap bandar.\n\n"
        "💡 *Tips:* Gunakan fitur **📈 Bet Tracker** untuk mencatat riwayat kemenangan dan menghitung ROI kamu secara otomatis!"
    )
    back_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu_main")]]
    )
    await safe_reply(update, text, reply_markup=back_kb)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command showing system diagnostics."""
    if settings.active_ai_provider == "gemini":
        ai_status = f"🟢 Google Gemini ({settings.gemini_model}) - 100% Gratis"
    elif settings.active_ai_provider == "openai":
        ai_status = f"🟢 OpenAI ({settings.openai_model})"
    else:
        ai_status = "🟡 Mode Heuristik & Statistik Matematika"

    rapid_status = "🟢 Terhubung" if settings.has_rapidapi else "🟡 Mode Fallback (Simulasi Kuat)"
    odds_status = "🟢 Terhubung" if settings.has_odds_api else "🟡 Mode Benchmark Sintetis"

    text = (
        "⚡ *STATUS SISTEM BOT 24/7* ⚡\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• 🤖 *AI Engine:* {ai_status}\n"
        f"• ⚽ *Football Data (RapidAPI):* {rapid_status}\n"
        f"• 🏦 *Market Odds (The Odds API):* {odds_status}\n"
        f"• 🌐 *Cloud Health Server:* Port `{settings.port}` (Aktif)\n"
        f"• 💾 *Sesi Analisis Aktif:* {len(_ACTIVE_REPORTS)} pengguna\n\n"
        "Status: *Berjalan Normal 24/7 Non-Stop* ✅"
    )
    back_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu_main")]]
    )
    await safe_reply(update, text, reply_markup=back_kb)


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear active user analysis session."""
    chat_id = update.effective_chat.id
    if chat_id in _ACTIVE_REPORTS:
        del _ACTIVE_REPORTS[chat_id]
        msg = "🗑 *Sesi analisis berhasil direset.* Kamu siap mengirim tiket parlay atau file PDF baru!"
    else:
        msg = "ℹ️ Tidak ada sesi analisis aktif saat ini. Silakan kirim tiket parlay atau file PDF baru."

    back_kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔥 Lihat AI Top Picks", callback_data="menu_top_picks")],
            [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_main")],
        ]
    )
    await safe_reply(update, msg, reply_markup=back_kb)


async def cmd_pdf_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed guide on sending PDF files."""
    text = (
        "📄 *PANDUAN ANALISIS 1 FOLDER PDF (MULTI-LAGA)* 📄\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Kamu tidak perlu mengirim screenshot satu per satu:\n\n"
        "1️⃣ *Kumpulkan Screenshot:*\n"
        "Ambil screenshot dari semua pertandingan atau tiket parlay yang ingin kamu pasang.\n\n"
        "2️⃣ *Jadikan 1 File PDF:*\n"
        "Gabungkan semua gambar tersebut ke dalam 1 file PDF (bisa menggunakan website gratis seperti *ilovepdf.com* atau fitur *Print to PDF* di HP).\n\n"
        "3️⃣ *Kirim ke Bot:*\n"
        "Cukup kirim file PDF tersebut ke chat ini sebagai dokumen. Bot akan otomatis:\n"
        "• Membaca seluruh halaman PDF via Gemini Vision.\n"
        "• Mengekstrak semua nama tim, pilihan taruhan, dan odds.\n"
        "• Menjalankan pemodelan statistik Poisson, +EV, dan taktik untuk seluruh laga sekaligus!"
    )
    back_kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⚽ Coba Contoh Demo Dulu", callback_data="menu_demo")],
            [InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu_main")],
        ]
    )
    await safe_reply(update, text, reply_markup=back_kb)


async def run_demo_parlay(update: Update):
    """Run a live demonstration analysis for 3 real match picks."""
    demo_legs = [
        Leg(
            home="Arsenal",
            away="Chelsea",
            pick="Over 2.5",
            odds=1.85,
            market=MarketCategory.OVER_UNDER,
            raw="Arsenal vs Chelsea - Over 2.5 @1.85",
        ),
        Leg(
            home="Real Madrid",
            away="Barcelona",
            pick="Real Madrid",
            odds=2.10,
            market=MarketCategory.MATCH_WINNER,
            raw="Real Madrid vs Barcelona - Real Madrid @2.10",
        ),
        Leg(
            home="Inter Milan",
            away="Juventus",
            pick="Under 2.5",
            odds=1.75,
            market=MarketCategory.OVER_UNDER,
            raw="Inter Milan vs Juventus - Under 2.5 @1.75",
        ),
    ]
    target = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if target:
        await target.reply_text(
            "⚽ *Menjalankan Analisis Contoh Tiket Parlay (3-Laga):*\n"
            "1. `Arsenal vs Chelsea` - Over 2.5 @1.85\n"
            "2. `Real Madrid vs Barcelona` - Real Madrid @2.10\n"
            "3. `Inter Milan vs Juventus` - Under 2.5 @1.75\n",
            parse_mode="Markdown",
        )
    await execute_analysis_flow(update, demo_legs)


async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /analyze command for single match analysis."""
    args = context.args
    if not args:
        await safe_reply(update, "Format: `/analyze Arsenal vs Chelsea`", parse_mode="Markdown")
        return

    raw_query = " ".join(args)
    legs = parse_legs(raw_query)
    if not legs:
        await safe_reply(
            update,
            "❌ Format tidak dikenali. Contoh: `/analyze Arsenal vs Chelsea` atau `Arsenal vs Chelsea - Over 2.5 @1.85`",
            parse_mode="Markdown",
        )
        return

    await execute_analysis_flow(update, legs)


# ---------------------------------------------------------------------------
# Message & Photo & Document Handlers
# ---------------------------------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming text messages and persistent menu buttons."""
    text = update.message.text.strip()
    if not text:
        return

    # Check for Reply Keyboard Button taps
    if text in ("🔥 AI Top Picks Hari Ini", "/toppicks"):
        await cmd_top_picks(update, context)
        return
    elif text in ("📅 Jadwal & Top Match", "/schedule"):
        await cmd_schedule(update, context)
        return
    elif text in ("🛡️ Optimasi Parlay", "/optimize"):
        await cmd_optimize(update, context)
        return
    elif text in ("📈 Bet Tracker & Win Rate", "/tracker"):
        await cmd_tracker(update, context)
        return
    elif text in ("💵 Atur Modal (Bankroll)", "/bankroll"):
        await cmd_bankroll(update, context)
        return
    elif text in ("🎯 Filter Pasaran", "/markets"):
        await cmd_markets(update, context)
        return
    elif text in ("⚽ Contoh Parlay (Demo)", "/demo"):
        await run_demo_parlay(update)
        return
    elif text == "📄 Cara Kirim PDF / Foto":
        await cmd_pdf_guide(update, context)
        return
    elif text == "📖 Panduan & Status AI":
        await cmd_help(update, context)
        return
    elif text == "🗑 Reset Sesi":
        await cmd_clear(update, context)
        return

    # Custom bankroll setting if user types e.g. "Rp 1.500.000" or numeric amount
    if text.lower().startswith("rp ") or (text.isdigit() and int(text) >= 10000):
        try:
            val_str = text.lower().replace("rp", "").replace(".", "").replace(",", "").strip()
            amount = float(val_str)
            saved = tracker.set_user_bankroll(update.effective_chat.id, amount)
            await update.message.reply_text(
                f"✅ *Bankroll berhasil diatur menjadi:* `{_format_rupiah(saved)}`\n"
                "Kalkulasi alokasi modal Kelly pada tiket analisis berikutnya akan otomatis mengikuti nominal ini.",
                reply_markup=get_main_menu_keyboard(),
                parse_mode="Markdown",
            )
            return
        except Exception:
            pass

    # Parse text as parlay ticket / match list
    legs = parse_legs(text)
    if not legs:
        await update.message.reply_text(
            "❌ Tidak ada pertandingan yang terdeteksi.\n\n"
            "Gunakan format teks:\n"
            "`Arsenal vs Chelsea - Over 2.5 @1.85`\n\n"
            "Atau kirim **file PDF / foto screenshot** tiket taruhan kamu.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="Markdown",
        )
        return

    await execute_analysis_flow(update, legs)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming screenshot photos using AI Vision."""
    status_msg = await update.message.reply_text("🔍 *Membaca slip taruhan via AI Vision...*", parse_mode="Markdown")

    try:
        photo = update.message.photo[-1]
        tg_file = await context.bot.get_file(photo.file_id)
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        image_bytes = buf.getvalue()

        legs = await extract_legs_from_image(image_bytes)

        try:
            await status_msg.delete()
        except Exception:
            pass

        if not legs:
            await update.message.reply_text(
                "❌ Gambar terbaca, namun tidak ada pertandingan atau pasaran yang terdeteksi.\n"
                "Pastikan gambar menampilkan nama tim dan odds dengan jelas, atau ketik manual.",
                reply_markup=get_main_menu_keyboard(),
                parse_mode="Markdown",
            )
            return

        await execute_analysis_flow(update, legs)

    except Exception as e:
        logger.exception("Error processing photo")
        try:
            await status_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(f"❌ Gagal memproses gambar: {e}", reply_markup=get_main_menu_keyboard())


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming PDF documents or image files containing multiple matches."""
    doc = update.message.document
    if not doc:
        return

    filename = doc.file_name or "document"
    mime_type = doc.mime_type or ""
    is_pdf = filename.lower().endswith(".pdf") or mime_type == "application/pdf"
    is_image = (
        filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        or mime_type.startswith("image/")
    )

    if not is_pdf and not is_image:
        await update.message.reply_text(
            "📄 *Format file tidak didukung.*\n"
            "Silakan kirim file **PDF (.pdf)** berisi kompilasi screenshot pertandingan, "
            "atau kirim foto langsung.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="Markdown",
        )
        return

    status_msg = await update.message.reply_text(
        f"📄 *Menerima dokumen:* `{filename}`\n"
        f"⏳ Mengunduh dan membaca semua pertandingan via AI Vision...",
        parse_mode="Markdown",
    )

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        file_bytes = buf.getvalue()

        if is_pdf:
            legs, total_pages = await extract_legs_from_pdf(file_bytes)
            page_info = f" ({total_pages} halaman)"
        else:
            legs = await extract_legs_from_image(file_bytes)
            page_info = ""

        try:
            await status_msg.delete()
        except Exception:
            pass

        if not legs:
            await update.message.reply_text(
                f"❌ Dokumen `{filename}`{page_info} terbaca, namun tidak ada pertandingan atau pasaran yang terdeteksi.\n"
                "Pastikan dokumen menampilkan nama tim dan odds dengan jelas.",
                reply_markup=get_main_menu_keyboard(),
                parse_mode="Markdown",
            )
            return

        await update.message.reply_text(
            f"✅ *Berhasil mengekstrak {len(legs)} pertandingan* dari PDF `{filename}`{page_info}!\n"
            f"Memulai analisis mendalam untuk seluruh pertandingan...",
            parse_mode="Markdown",
        )

        await execute_analysis_flow(update, legs)

    except Exception as e:
        logger.exception("Error processing document")
        try:
            await status_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(f"❌ Gagal memproses dokumen `{filename}`: {e}", reply_markup=get_main_menu_keyboard())


# ---------------------------------------------------------------------------
# Pipeline Execution & Callback Queries
# ---------------------------------------------------------------------------

async def execute_analysis_flow(update: Update, legs: list[Leg]):
    """Execute deep multi-layer analysis and render the main parlay report."""
    target_msg = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    status_msg = None
    if target_msg:
        status_msg = await target_msg.reply_text(
            f"⏳ *Memproses analisis mendalam untuk {len(legs)} pertandingan...*\n"
            f"• Menghitung Poisson Expected Goals (xG)...\n"
            f"• Menghitung Expected Value (+EV) & Kelly Stake...\n"
            f"• Mensintesis taktik & peluang pasar...",
            parse_mode="Markdown",
        )

    try:
        report = await analyze_parlay(legs)

        # Store report in cache for interactive drill-downs
        chat_id = update.effective_chat.id
        _ACTIVE_REPORTS[chat_id] = report

        if status_msg:
            try:
                await status_msg.delete()
            except Exception:
                pass

        summary_text, reply_markup = format_parlay_overview(report, user_id=chat_id)
        await safe_reply(update, summary_text, reply_markup=reply_markup)

    except Exception as e:
        logger.exception("Analysis pipeline error")
        if status_msg:
            try:
                await status_msg.delete()
            except Exception:
                pass
        await safe_reply(update, f"❌ Terjadi kesalahan saat menganalisis: {e}", parse_mode=None)


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle interactive inline keyboard navigation across all features."""
    query = update.callback_query
    await query.answer()

    data = query.data
    chat_id = update.effective_chat.id

    # 1. Main Menu Navigation
    if data == "menu_main":
        text = "📋 *DASHBOARD MENU UTAMA*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nSilakan pilih fitur di bawah:"
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard())
        except Exception:
            await safe_reply(update, text, reply_markup=get_main_menu_keyboard())
        return

    # 2. Top Picks Navigation
    elif data == "menu_top_picks":
        picks = top_picks.get_daily_top_picks()
        text, markup = format_top_picks_view(picks)
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            await safe_reply(update, text, reply_markup=markup)
        return

    elif data.startswith("top_analyze_"):
        pick_id = data.replace("top_analyze_", "")
        pick_item = top_picks.get_top_pick_by_id(pick_id)
        if pick_item:
            leg = top_picks.convert_top_pick_to_leg(pick_item)
            await execute_analysis_flow(update, [leg])
        return

    elif data == "top_parlay_all":
        picks = top_picks.get_daily_top_picks()
        all_legs = [top_picks.convert_top_pick_to_leg(p) for p in picks]
        await execute_analysis_flow(update, all_legs)
        return

    # 3. Schedule Navigation
    elif data == "menu_schedule":
        sched_data = schedule.get_marquee_schedule()
        text, markup = format_schedule_view(sched_data)
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            await safe_reply(update, text, reply_markup=markup)
        return

    elif data.startswith("sched_analyze_"):
        match_id = data.replace("sched_analyze_", "")
        match_info = schedule.get_schedule_match_by_id(match_id)
        if match_info:
            leg = schedule.convert_schedule_match_to_leg(match_info)
            await execute_analysis_flow(update, [leg])
        return

    elif data == "sched_parlay_all":
        all_dict = schedule.get_marquee_schedule()
        all_legs = []
        for l_matches in all_dict.values():
            for m in l_matches[:2]:  # take top 2 per league for mega parlay
                all_legs.append(schedule.convert_schedule_match_to_leg(m))
        await execute_analysis_flow(update, all_legs)
        return

    # 4. Bankroll Management
    elif data == "menu_bankroll":
        text, markup = format_bankroll_calculator_view(chat_id)
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            await safe_reply(update, text, reply_markup=markup)
        return

    elif data.startswith("set_bankroll_"):
        amount_str = data.replace("set_bankroll_", "")
        amount = float(amount_str)
        saved = tracker.set_user_bankroll(chat_id, amount)
        text = (
            f"✅ *Bankroll Berhasil Disimpan:*\n`{_format_rupiah(saved)}`\n\n"
            "Seluruh rekomendasi nominal pasang Rupiah di tiket parlay dan single akan otomatis dihitung berdasarkan modal ini."
        )
        await safe_reply(update, text, reply_markup=get_main_menu_keyboard())
        return

    # 5. Bet Tracker Navigation
    elif data == "menu_tracker":
        text, markup = format_tracker_dashboard(chat_id)
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            await safe_reply(update, text, reply_markup=markup)
        return

    elif data == "track_save_parlay":
        report = _ACTIVE_REPORTS.get(chat_id)
        if not report:
            await query.answer("⚠️ Sesi analisis tidak ditemukan.", show_alert=True)
            return

        bankroll = tracker.get_user_bankroll(chat_id)
        rec_stake = bankroll * report.recommended_kelly_stake
        legs_str = " + ".join(f"{m.leg.home} ({m.leg.pick})" for m in report.matches)
        title = f"Parlay {len(report.matches)} Laga"
        bet_id = tracker.save_bet(
            user_id=chat_id,
            ticket_title=title,
            legs_summary=legs_str,
            odds=report.combined_odds,
            stake_amount=rec_stake,
        )
        await query.answer(f"✅ Tiket Parlay #{bet_id} berhasil disimpan ke Bet Tracker!", show_alert=True)
        text, markup = format_tracker_dashboard(chat_id)
        await safe_reply(update, text, reply_markup=markup)
        return

    elif data.startswith("track_save_single_"):
        report = _ACTIVE_REPORTS.get(chat_id)
        if not report:
            await query.answer("⚠️ Sesi tidak ditemukan.", show_alert=True)
            return
        idx = int(data.replace("track_save_single_", ""))
        if 0 <= idx < len(report.matches):
            m = report.matches[idx]
            bankroll = tracker.get_user_bankroll(chat_id)
            single_stake = bankroll * m.kelly_fractional_stake
            title = f"Single: {m.leg.clean_title()}"
            summary = f"{m.leg.pick} @{m.leg.odds:.2f}"
            bet_id = tracker.save_bet(chat_id, title, summary, m.leg.odds, single_stake)
            await query.answer(f"✅ Laga Single #{bet_id} disimpan ke Bet Tracker!", show_alert=True)
        return

    elif data.startswith("settle_"):
        # Format: settle_<bet_id>_<WIN|LOSE|VOID>
        parts = data.split("_")
        bet_id = int(parts[1])
        result = parts[2]
        tracker.settle_bet(bet_id, chat_id, result)
        await query.answer(f"✅ Tiket #{bet_id} diselesaikan sebagai {result}!", show_alert=True)
        text, markup = format_tracker_dashboard(chat_id)
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            await safe_reply(update, text, reply_markup=markup)
        return

    # 6. Parlay Optimizer Navigation
    elif data == "opt_parlay":
        report = _ACTIVE_REPORTS.get(chat_id)
        if not report:
            # Create demo parlay if no active report
            demo_legs = [
                Leg("Arsenal", "Chelsea", "Over 2.5", 1.85, MarketCategory.OVER_UNDER),
                Leg("Real Madrid", "Barcelona", "Real Madrid Win", 2.10, MarketCategory.MATCH_WINNER),
                Leg("Inter Milan", "Juventus", "Under 2.5", 1.75, MarketCategory.OVER_UNDER),
                Leg("Manchester United", "Liverpool", "Man United Win", 3.20, MarketCategory.MATCH_WINNER),
            ]
            report = await analyze_parlay(demo_legs)
            _ACTIVE_REPORTS[chat_id] = report

        opt = optimize_parlay(report)
        text, markup = format_optimized_parlay_view(opt, chat_id)
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            await safe_reply(update, text, reply_markup=markup)
        return

    elif data == "opt_run_safe":
        report = _ACTIVE_REPORTS.get(chat_id)
        if report:
            opt = optimize_parlay(report)
            safe_legs = [m.leg for m in opt.safe_legs]
            if safe_legs:
                await execute_analysis_flow(update, safe_legs)
        return

    elif data == "opt_run_value":
        report = _ACTIVE_REPORTS.get(chat_id)
        if report:
            opt = optimize_parlay(report)
            value_legs = [m.leg for m in opt.value_legs]
            if value_legs:
                await execute_analysis_flow(update, value_legs)
        return

    # 7. Specialized Market Filters
    elif data == "menu_market_filter":
        text, markup = format_market_filter_view()
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            await safe_reply(update, text, reply_markup=markup)
        return

    elif data.startswith("market_filter_"):
        m_type = data.replace("market_filter_", "")
        picks = top_picks.get_daily_top_picks()
        if m_type == "ou":
            filtered = [p for p in picks if p.market == MarketCategory.OVER_UNDER]
            title = "⚽ *TOP PICKS: OVER / UNDER TOTAL GOL*"
        elif m_type == "btts":
            filtered = [p for p in picks if p.market == MarketCategory.BTTS]
            title = "🤝 *TOP PICKS: BOTH TEAMS TO SCORE (BTTS)*"
        elif m_type == "hdp":
            filtered = [p for p in picks if p.market == MarketCategory.HANDICAP]
            title = "🚩 *TOP PICKS: ASIAN HANDICAP (VOOR)*"
        else:
            filtered = [p for p in picks if p.market == MarketCategory.MATCH_WINNER]
            title = "🏆 *TOP PICKS: 1X2 MATCH WINNER*"

        if not filtered:
            filtered = picks[:2]

        text, markup = format_top_picks_view(filtered)
        text = f"{title}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n" + text
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            await safe_reply(update, text, reply_markup=markup)
        return

    # 8. Help, Status, Clear, Demo
    elif data == "menu_demo":
        await run_demo_parlay(update)
        return
    elif data == "menu_pdf_guide":
        await cmd_pdf_guide(update, context)
        return
    elif data == "menu_status":
        await cmd_status(update, context)
        return
    elif data == "menu_help":
        await cmd_help(update, context)
        return
    elif data == "menu_clear":
        await cmd_clear(update, context)
        return

    # 9. Match Report Drill-downs
    report = _ACTIVE_REPORTS.get(chat_id)
    if not report:
        await query.edit_message_text(
            "⚠️ Sesi analisis sudah kedaluwarsa. Silakan kirim tiket atau pertandingan baru.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    if data == "back_summary":
        summary_text, reply_markup = format_parlay_overview(report, user_id=chat_id)
        try:
            await query.edit_message_text(summary_text, parse_mode="Markdown", reply_markup=reply_markup)
        except BadRequest:
            await query.edit_message_text(summary_text, parse_mode=None, reply_markup=reply_markup)

    elif data.startswith("match_"):
        try:
            match_idx = int(data.split("_")[1])
            if 0 <= match_idx < len(report.matches):
                match_analysis = report.matches[match_idx]
                detail_text, reply_markup = format_single_match_deep_dive(
                    match_analysis, match_idx, len(report.matches), user_id=chat_id
                )
                try:
                    await query.edit_message_text(detail_text, parse_mode="Markdown", reply_markup=reply_markup)
                except BadRequest:
                    await query.edit_message_text(detail_text, parse_mode=None, reply_markup=reply_markup)
        except Exception as e:
            logger.warning(f"Error handling match callback: {e}")


# ---------------------------------------------------------------------------
# 24/7 Cloud HTTP Health Server (Render, Railway, Koyeb, Fly.io)
# ---------------------------------------------------------------------------

async def _http_client_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Handle health check HTTP requests from cloud hosting or UptimeRobot."""
    try:
        await reader.readline()
        while True:
            line = await reader.readline()
            if not line or line in (b"\r\n", b"\n"):
                break

        body = json.dumps(
            {
                "status": "healthy",
                "service": "Deep Football Parlay Analyzer Suite",
                "uptime": "24/7 live",
                "timestamp": int(time.time()),
            }
        ).encode("utf-8")

        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(body)).encode("utf-8") + b"\r\n"
            b"Connection: close\r\n"
            b"\r\n" + body
        )
        writer.write(response)
        await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def start_http_server():
    """Start non-blocking HTTP server for cloud platforms requiring open ports."""
    port = settings.port
    host = settings.host
    try:
        server = await asyncio.start_server(_http_client_handler, host, port)
        logger.info(f"🌐 24/7 Cloud Health Check HTTP Server aktif di http://{host}:{port}")
        return server
    except Exception as e:
        logger.warning(f"Could not bind HTTP server to {host}:{port} ({e})")
        return None


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

async def main():
    """Main asynchronous entry point initializing Telegram Bot and HTTP Server."""
    if not settings.has_telegram:
        print("\n❌ ERROR: TELEGRAM_BOT_TOKEN belum disetel di file .env!")
        print("Silakan isi file .env dengan token bot kamu.")
        return

    logger.info("Memulai Deep Football & Parlay Analysis Telegram Bot with Full Suite...")

    # 1. Initialize SQLite Database
    tracker.init_db()

    # 2. Start HTTP Health Server in background (for 24/7 cloud hosting)
    http_server = await start_http_server()

    # 3. Build Telegram Application
    app = Application.builder().token(settings.telegram_bot_token).build()

    # Set up Telegram native menu commands list
    try:
        commands = [
            BotCommand("start", "Mulai & Buka Dashboard Utama"),
            BotCommand("menu", "Tampilkan Menu Pilihan Fitur"),
            BotCommand("toppicks", "🔥 AI Top Picks of the Day"),
            BotCommand("schedule", "📅 Jadwal Laga & 1-Klik Analisis"),
            BotCommand("tracker", "📈 Personal Bet Tracker & Win-Rate"),
            BotCommand("bankroll", "💵 Atur Modal & Staking Rp"),
            BotCommand("optimize", "🛡️ Optimasi Parlay & Filter Trap"),
            BotCommand("markets", "🎯 Filter Khusus Pasaran"),
            BotCommand("demo", "⚽ Contoh Analisis Parlay (3-Laga)"),
            BotCommand("help", "📖 Panduan Lengkap & Metrik"),
            BotCommand("status", "📊 Cek Status Server & AI"),
            BotCommand("clear", "🗑 Reset Sesi Analisis"),
        ]
        await app.bot.set_my_commands(commands)
        logger.info("✅ Telegram Bot Commands Menu berhasil didaftarkan.")
    except Exception as e:
        logger.warning(f"Could not register Telegram commands: {e}")

    # Register Handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("toppicks", cmd_top_picks))
    app.add_handler(CommandHandler("schedule", cmd_schedule))
    app.add_handler(CommandHandler("tracker", cmd_tracker))
    app.add_handler(CommandHandler("bankroll", cmd_bankroll))
    app.add_handler(CommandHandler("optimize", cmd_optimize))
    app.add_handler(CommandHandler("markets", cmd_markets))
    app.add_handler(CommandHandler("demo", lambda u, c: run_demo_parlay(u)))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("analyze", cmd_analyze))

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # 4. Start Long Polling
    async with app:
        await app.start()
        await app.updater.start_polling()
        logger.info("✅ Bot berhasil tersambung ke Telegram dan siap melayani 24/7.")

        # Keep running indefinitely until interrupted
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Bot dihentikan.")
        finally:
            await app.updater.stop()
            await app.stop()
            if http_server:
                http_server.close()
                await http_server.wait_closed()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
