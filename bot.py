"""
bot.py — Deep Football & Parlay Analysis Telegram Bot with 24/7 Cloud Support & Interactive Menu System.
Integrates:
- Google Gemini (Free) & OpenAI Vision for PDF/image slip extraction
- Bivariate Poisson xG modeling & true probability estimation
- Bookmaker market consensus & zero-vig fair odds
- Deep qualitative AI tactical analysis
- Expected Value (+EV) & Fractional Kelly staking
- Interactive Telegram Inline & Reply Keyboard Menu System
- Built-in HTTP health check server for 24/7 cloud hosting
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
from formatter import format_parlay_overview, format_single_match_deep_dive

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
        [KeyboardButton("⚽ Contoh Parlay (Demo)"), KeyboardButton("📄 Cara Kirim PDF / Foto")],
        [KeyboardButton("📊 Status Server & AI"), KeyboardButton("📖 Panduan Lengkap")],
        [KeyboardButton("🗑 Reset Sesi")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for dashboard navigation."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⚽ Analisis Contoh Parlay 3-Laga (1-Klik)", callback_data="menu_demo")],
            [InlineKeyboardButton("📄 Panduan Kirim File PDF / Foto", callback_data="menu_pdf_guide")],
            [InlineKeyboardButton("📊 Cek Status AI & Server", callback_data="menu_status")],
            [InlineKeyboardButton("📖 Panduan Metrik (+EV, Kelly, xG)", callback_data="menu_help")],
            [InlineKeyboardButton("🗑 Reset Sesi Analisis", callback_data="menu_clear")],
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
        "🏆 *SELAMAT DATANG DI DEEP FOOTBALL & PARLAY ANALYZER* 🏆\n\n"
        "Bot ini melakukan analisis pertandingan sepak bola dan tiket parlay secara profesional, "
        "menggabungkan model matematika kuantitatif (Poisson xG, True Probability, +EV, Kelly Staking) "
        "dan analisa taktis mendalam berbasis AI.\n\n"
        "✨ *Pilih menu di bawah atau kirim data langsung:*\n"
        "• Kirim **1 file PDF** berisi kumpulan screenshot pertandingan.\n"
        "• Kirim **foto screenshot** slip taruhan langsung.\n"
        "• Kirim teks daftar laga: `Arsenal vs Chelsea - Over 2.5 @1.85`\n\n"
        "Gunakan tombol menu di bawah untuk kemudahan navigasi 👇"
    )
    if update.message:
        await update.message.reply_text(
            text,
            reply_markup=MAIN_REPLY_KEYBOARD,
            parse_mode="Markdown",
        )
        await update.message.reply_text(
            "📋 *DASHBOARD MENU UTAMA:*",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="Markdown",
        )
    else:
        await safe_reply(update, text, reply_markup=get_main_menu_keyboard())


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /menu command displaying the interactive dashboard."""
    text = (
        "📋 *DASHBOARD MENU UTAMA*\n\n"
        "Silakan pilih aksi yang ingin kamu lakukan:"
    )
    await safe_reply(update, text, reply_markup=get_main_menu_keyboard())


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command with detailed manual."""
    text = (
        "📖 *PANDUAN LENGKAP PENGGUNAAN BOT*\n\n"
        "📌 *1. Cara Kirim Tiket:*\n"
        "• *File PDF (Disarankan):* Masukkan screenshot seluruh laga ke dalam 1 file PDF, lalu kirim ke bot. Bot membaca semua halaman otomatis.\n"
        "• *Foto:* Kirim foto screenshot slip taruhan biasa.\n"
        "• *Teks Manual:* `Tim A vs Tim B - Pilihan @Odds`\n"
        "  Contoh: `Arsenal vs Chelsea - Over 2.5 @1.85`\n\n"
        "📌 *2. Arti Istilah dalam Laporan:*\n"
        "• *+EV (Expected Value):* Keuntungan matematis jangka panjang. Nilai positif (+EV) artinya odds bandar terlalu murah dibanding peluang aslinya.\n"
        "• *True Prob:* Probabilitas murni hasil simulasi Poisson tanpa potongan komisi bandar.\n"
        "• *Kelly Staking:* Rekomendasi alokasi modal maksimal agar terhindar dari resiko drawdown/bangkrut.\n"
        "• *Core Anchor:* Laga paling solid yang sangat direkomendasikan menjadi fondasi parlay kamu.\n\n"
        "💡 *Tips:* Klik tombol laga di bawah laporan untuk melihat ulasan taktik, kelemahan, dan jebakan bandar per pertandingan."
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
        "⚡ *STATUS SISTEM BOT 24/7* ⚡\n\n"
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
        msg = "🗑 *Sesi analisis berhasil direset.* Kamu siap mengirim tiket parlay atau pertandingan baru!"
    else:
        msg = "ℹ️ Tidak ada sesi analisis aktif saat ini. Silakan kirim tiket parlay atau file PDF baru."

    back_kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⚽ Mulai Contoh Parlay", callback_data="menu_demo")],
            [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_main")],
        ]
    )
    await safe_reply(update, msg, reply_markup=back_kb)


async def cmd_pdf_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed guide on sending PDF files."""
    text = (
        "📄 *PANDUAN ANALISIS 1 FOLDER PDF*\n\n"
        "Kamu tidak perlu mengirim screenshot satu per satu:\n\n"
        "1️⃣ *Kumpulkan Screenshot:*\n"
        "Ambil screenshot dari semua pertandingan atau tiket parlay yang ingin kamu pasang.\n\n"
        "2️⃣ *Jadikan 1 File PDF:*\n"
        "Gabungkan semua gambar tersebut ke dalam 1 file PDF (bisa pakai website gratis seperti *ilovepdf.com* atau fitur *Print to PDF* di HP).\n\n"
        "3️⃣ *Kirim ke Bot:*\n"
        "Cukup kirim file PDF tersebut ke chat ini sebagai dokumen. Bot akan otomatis:\n"
        "• Membaca seluruh halaman PDF via AI Vision.\n"
        "• Mengekstrak semua nama tim, pilihan taruhan, dan odds.\n"
        "• Menganalisis setiap pertandingan satu per satu sekaligus!"
    )
    back_kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⚽ Coba Contoh Analisis Dulu", callback_data="menu_demo")],
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
    if text in ("⚽ Contoh Parlay (Demo)", "/demo"):
        await run_demo_parlay(update)
        return
    elif text == "📄 Cara Kirim PDF / Foto":
        await cmd_pdf_guide(update, context)
        return
    elif text == "📊 Status Server & AI":
        await cmd_status(update, context)
        return
    elif text == "📖 Panduan Lengkap":
        await cmd_help(update, context)
        return
    elif text == "🗑 Reset Sesi":
        await cmd_clear(update, context)
        return

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

        summary_text, reply_markup = format_parlay_overview(report)
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
    """Handle interactive inline keyboard navigation."""
    query = update.callback_query
    await query.answer()

    data = query.data
    chat_id = update.effective_chat.id

    # 1. Global Menu Actions (do not require active report)
    if data == "menu_main":
        text = "📋 *DASHBOARD MENU UTAMA*\n\nSilakan pilih menu di bawah:"
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard())
        except Exception:
            await safe_reply(update, text, reply_markup=get_main_menu_keyboard())
        return

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

    # 2. Report Drill-down Navigation (requires active report)
    report = _ACTIVE_REPORTS.get(chat_id)
    if not report:
        await query.edit_message_text(
            "⚠️ Sesi analisis sudah kedaluwarsa. Silakan kirim tiket atau pertandingan baru.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    if data == "back_summary":
        summary_text, reply_markup = format_parlay_overview(report)
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
                    match_analysis, match_idx, len(report.matches)
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
                "service": "Deep Football Parlay Analyzer",
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

    logger.info("Memulai Deep Football & Parlay Analysis Telegram Bot...")

    # 1. Start HTTP Health Server in background (for 24/7 cloud hosting)
    http_server = await start_http_server()

    # 2. Build Telegram Application
    app = Application.builder().token(settings.telegram_bot_token).build()

    # Set up Telegram native menu commands list
    try:
        commands = [
            BotCommand("start", "Mulai & Tampilkan Menu Utama"),
            BotCommand("menu", "Buka Dashboard Menu Pilihan"),
            BotCommand("demo", "Analisis Contoh Parlay (1-Klik)"),
            BotCommand("status", "Cek Status AI & Server"),
            BotCommand("help", "Panduan Penggunaan Lengkap"),
            BotCommand("clear", "Reset Sesi Analisis"),
        ]
        await app.bot.set_my_commands(commands)
        logger.info("✅ Telegram Bot Commands Menu berhasil didaftarkan.")
    except Exception as e:
        logger.warning(f"Could not register Telegram commands: {e}")

    # Register Handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("demo", lambda u, c: run_demo_parlay(u)))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(CommandHandler("analyze", cmd_analyze))

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # 3. Start Long Polling
    async with app:
        await app.start()
        await app.updater.start_polling()
        logger.info("✅ Bot berhasil tersambung ke Telegram dan siap menerima pesan 24/7.")

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
