"""
bot.py — Deep Football & Parlay Analysis Telegram Bot with 24/7 Cloud Support.
Integrates:
- OpenAI Vision for bet slip screenshot reading
- Bivariate Poisson xG modeling & true probability estimation
- Bookmaker market consensus & zero-vig fair odds
- Deep qualitative AI tactical analysis (GPT-4o)
- Expected Value (+EV) & Fractional Kelly staking
- Interactive Telegram Inline UI
- Built-in HTTP health check server for 24/7 cloud hosting (Render / Railway / Koyeb)
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import sys
import time

from telegram import Update
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
from models import Leg, ParlayAnalysisReport
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
        await target.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except BadRequest as e:
        if "can't parse entities" in str(e).lower() or "markdown" in str(e).lower():
            logger.warning("Markdown parsing failed, sending plain text fallback")
            await target.reply_text(text, parse_mode=None, reply_markup=reply_markup)
        else:
            raise e


# ---------------------------------------------------------------------------
# Command Handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command with rich greeting and instructions."""
    text = (
        "🏆 *SELAMAT DATANG DI DEEP FOOTBALL & PARLAY ANALYZER* 🏆\n\n"
        "Bot ini melakukan analisis pertandingan sepak bola dan tiket parlay dengan *kedalaman tingkat profesional*, "
        "menggabungkan pemodelan matematika kuantitatif dan analisis taktis mendalam.\n\n"
        "✨ *Fitur Utama:*\n"
        "• 📐 *Model Poisson & xG:* Proyeksi gol ekspektasi dan skor probabilitas tertinggi.\n"
        "• 📊 *True Probability & Nilai EV:* Menghitung Expected Value (+EV) bebas margin bandar.\n"
        "• 💰 *Kelly Criterion Staking:* Rekomendasi alokasi modal terukur agar aman dari drawdown.\n"
        "• 🧠 *AI Tactical Breakdown:* Analisis benturan gaya main, kelemahan taktis, dan peringatan jebakan bandar.\n"
        "• 📷 *Vision Slip Parser:* Kirim screenshot tiket parlay, bot otomatis membaca semua taruhan!\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🚀 *Cara Menggunakan:*\n\n"
        "1️⃣ *Kirim Teks Tiket Parlay (Multi-Laga):*\n"
        "`Arsenal vs Chelsea - Over 2.5 @1.85`\n"
        "`Real Madrid vs Barcelona - Real Madrid @2.10`\n"
        "`Inter vs Juventus - Under 2.5 @1.75`\n\n"
        "2️⃣ *Kirim Foto / Dokumen PDF (Multi-Laga):*\n"
        "• Kirim foto slip taruhan (SBOBET, Bet365, Parlay slip, dll).\n"
        "• Atau kirim **1 file PDF** berisi kumpulan screenshot semua pertandingan! Bot akan membaca seluruh halaman dan menganalisis setiap laga otomatis.\n\n"
        "3️⃣ *Analisis Cepat Satu Laga:*\n"
        "`/analyze Arsenal vs Chelsea`\n\n"
        "Ketik /help untuk panduan lengkap atau /status untuk memeriksa koneksi sistem."
    )
    await safe_reply(update, text)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command with detailed manual."""
    text = (
        "📖 *PANDUAN LENGKAP PENGGUNAAN BOT*\n\n"
        "📌 *Format Teks yang Didukung:*\n"
        "`Tim A vs Tim B - Pilihan @Odds`\n\n"
        "Contoh variasi input:\n"
        "• `Arsenal vs Chelsea - Over 2.5 @1.85`\n"
        "• `Milan vs Inter - Draw @3.40`\n"
        "• `Liverpool vs Man City - Both Teams to Score @1.65`\n"
        "• `Bayern vs Dortmund - Bayern -1.5 @2.05`\n\n"
        "📌 *Arti Istilah dalam Laporan:*\n"
        "• *+EV (Expected Value):* Keuntungan matematis jangka panjang. Jika +EV positif (>0%), taruhan tersebut bernilai tinggi di atas harga bandar.\n"
        "• *True Prob:* Probabilitas murni hasil simulasi model statistik (tanpa potongan komisi bandar).\n"
        "• *Kelly Staking:* Persentase modal maksimal yang disarankan agar terhindar dari resiko bangkrut.\n"
        "• *Core Anchor:* Laga paling stabil yang sangat direkomendasikan menjadi fondasi parlay kamu.\n\n"
        "📸 *Tips Screenshot:* Pastikan gambar slip taruhan tidak blur dan nama tim serta pasaran terbaca jelas."
    )
    await safe_reply(update, text)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if settings.active_ai_provider == "gemini":
        ai_status = f"🟢 Google Gemini ({settings.gemini_model}) - 100% Gratis"
    elif settings.active_ai_provider == "openai":
        ai_status = f"🟢 OpenAI ({settings.openai_model})"
    else:
        ai_status = "🟡 Mode Heuristik & Statistik Matematika"

    rapid_status = "🟢 Terhubung" if settings.has_rapidapi else "🟡 Mode Fallback"
    odds_status = "🟢 Terhubung" if settings.has_odds_api else "🟡 Mode Estimasi Sintetis"

    text = (
        "⚡ *STATUS SISTEM BOT 24/7* ⚡\n\n"
        f"• 🤖 *AI Engine:* {ai_status}\n"
        f"• ⚽ *Football Data (RapidAPI):* {rapid_status}\n"
        f"• 🏦 *Market Odds (The Odds API):* {odds_status}\n"
        f"• 🌐 *Cloud Health Server:* Port `{settings.port}` (Aktif)\n"
        f"• 💾 *Sesi Analisis Aktif:* {len(_ACTIVE_REPORTS)} pengguna\n\n"
        "Status: *Berjalan Normal 24/7 Non-Stop* ✅"
    )
    await safe_reply(update, text)


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
# Message & Photo Handlers
# ---------------------------------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming text messages."""
    text = update.message.text.strip()
    if not text:
        return

    legs = parse_legs(text)
    if not legs:
        await update.message.reply_text(
            "❌ Tidak ada pertandingan yang terdeteksi.\n\n"
            "Gunakan format:\n"
            "`Arsenal vs Chelsea - Over 2.5 @1.85`\n\n"
            "Atau kirim foto screenshot tiket taruhan kamu.",
            parse_mode="Markdown",
        )
        return

    await execute_analysis_flow(update, legs)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming screenshot photos using OpenAI Vision."""
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
        await update.message.reply_text(f"❌ Gagal memproses gambar: {e}")


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
        await update.message.reply_text(f"❌ Gagal memproses dokumen `{filename}`: {e}")
# ---------------------------------------------------------------------------
# Pipeline Execution & Callback Queries
# ---------------------------------------------------------------------------

async def execute_analysis_flow(update: Update, legs: list[Leg]):
    """Execute deep multi-layer analysis and render the main parlay report."""
    target_msg = update.message
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

        try:
            await status_msg.delete()
        except Exception:
            pass

        summary_text, reply_markup = format_parlay_overview(report)
        await safe_reply(update, summary_text, reply_markup=reply_markup)

    except Exception as e:
        logger.exception("Analysis pipeline error")
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

    report = _ACTIVE_REPORTS.get(chat_id)
    if not report:
        await query.edit_message_text(
            "⚠️ Sesi analisis sudah kedaluwarsa. Silakan kirim tiket atau pertandingan baru.",
            reply_markup=None,
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

    # Register Handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
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
