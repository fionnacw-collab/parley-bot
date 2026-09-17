"""
bot.py — Main Controller for SBOBET AI Match & Parlay Suite with Live Match Timeline Monitoring.
Integrates:
- Gemini Universal Router for Natural Text, Sportsbook Screenshots, & Multi-Page PDFs
- SBOBET Market Suite (Asian Handicap HDP, Over/Under, BTTS, 1X2) & Poisson xG Engine
- Real-Time Live Match Feeds (soccervital.com) for Today & Tomorrow
- Background Live Slip Monitor & Real-Time Goal / FT Timeline Notifier
- Persistent SQLite Bet Tracker with Win-Rate & ROI Analytics
- Bankroll & Staking Calculator in Indonesian Rupiah (Kelly Criterion)
- 24/7 Cloud HTTP Health Server
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
from models import DeepMatchAnalysis, ExtractedMatch, ParlayAnalysisReport
import gemini_extractor
import sbobet_engine
import live_feed
import tracker
from live_monitor import start_live_monitor_worker
from formatter import (
    _format_rupiah,
    format_bankroll_view,
    format_live_schedule_view,
    format_parlay_analysis,
    format_single_match_analysis,
    format_tracker_dashboard,
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("ParleyBot")

_ACTIVE_ANALYSES: dict[int, tuple[str, DeepMatchAnalysis | ParlayAnalysisReport]] = {}
_BOT_ACTIVE_STATE: bool = True


def parse_currency_amount(text: str) -> float | None:
    """
    Parse informal Indonesian currency inputs:
    - '40.000', '40,000', '40000' -> 40000.0
    - '50k', '50rb', '500k', '500rb' -> 50000.0 / 500000.0
    - '1jt', '1.5jt', '2 juta', '2.5jt' -> 1000000.0 / 1500000.0 / 2500000.0
    - 'Rp 40.000', 'rp40.000' -> 40000.0
    """
    import re
    clean = text.lower().strip()
    if clean.startswith("/bankroll"):
        clean = clean.replace("/bankroll", "").strip()
    if clean.startswith("rp"):
        clean = clean[2:].strip()

    m_jt = re.match(r"^([\d.,]+)\s*(?:jt|juta)$", clean)
    if m_jt:
        num_part = m_jt.group(1).replace(",", ".")
        try:
            return float(num_part) * 1_000_000.0
        except Exception:
            pass

    m_k = re.match(r"^([\d.,]+)\s*(?:k|rb|ribu)$", clean)
    if m_k:
        num_part = m_k.group(1).replace(",", ".")
        try:
            return float(num_part) * 1_000.0
        except Exception:
            pass

    if re.match(r"^[\d.,]+$", clean):
        raw_digits = clean.replace(".", "").replace(",", "").strip()
        if raw_digits.isdigit():
            val = float(raw_digits)
            if val >= 1000.0:
                return val

    return None
# Persistent Bottom Reply Keyboard
# ---------------------------------------------------------------------------
MAIN_REPLY_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📅 Jadwal Laga (Hari Ini / Besok)"), KeyboardButton("📈 Bet Tracker & Live Skor")],
        [KeyboardButton("💵 Atur Modal (Bankroll)"), KeyboardButton("📖 Panduan & Cara Pakai")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for rich interactive dashboard navigation."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📅 Jadwal Laga Real-Time (Hari Ini & Besok)", callback_data="menu_schedule")],
            [
                InlineKeyboardButton("📈 Bet Tracker & Skor Live", callback_data="menu_tracker"),
                InlineKeyboardButton("💵 Atur Modal Bankroll", callback_data="menu_bankroll"),
            ],
            [
                InlineKeyboardButton("📖 Panduan Penggunaan", callback_data="menu_help"),
                InlineKeyboardButton("📊 Status Server & AI", callback_data="menu_status"),
            ],
        ]
    )


# ---------------------------------------------------------------------------
# Telegram Reply Helpers
# ---------------------------------------------------------------------------

def _split_message_chunks(text: str, max_chars: int = 3800) -> list[str]:
    """Split long text into clean chunks under Telegram's 4096 character limit."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    current_chunk = []
    current_len = 0

    for p in text.split("\n\n"):
        p_len = len(p) + 2
        if current_len + p_len <= max_chars:
            current_chunk.append(p)
            current_len += p_len
        else:
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_len = 0

            if len(p) > max_chars:
                for l in p.splitlines():
                    l_len = len(l) + 1
                    if current_len + l_len <= max_chars:
                        current_chunk.append(l)
                        current_len += l_len
                    else:
                        if current_chunk:
                            chunks.append("\n".join(current_chunk))
                        current_chunk = [l]
                        current_len = l_len
            else:
                current_chunk.append(p)
                current_len = p_len

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


async def safe_reply(
    update: Update,
    text: str,
    reply_markup=None,
    parse_mode: str | None = "Markdown",
):
    """Send reply with Markdown, automatically splitting long text into multiple messages."""
    target = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if not target:
        return

    chunks = _split_message_chunks(text, max_chars=3800)
    num_chunks = len(chunks)

    for idx, chunk in enumerate(chunks):
        # Attach inline keyboard only to the final message chunk
        markup = reply_markup if idx == num_chunks - 1 else None
        try:
            if update.callback_query and idx == 0 and num_chunks == 1:
                try:
                    await update.callback_query.edit_message_text(
                        chunk,
                        reply_markup=markup,
                        parse_mode=parse_mode,
                    )
                    continue
                except Exception:
                    pass

            await target.reply_text(
                chunk,
                reply_markup=markup,
                parse_mode=parse_mode,
            )
        except BadRequest as e:
            if "can't parse entities" in str(e).lower() and parse_mode:
                await target.reply_text(chunk, reply_markup=markup, parse_mode=None)
            else:
                logger.warning(f"Error sending message chunk: {e}")
                try:
                    await target.reply_text(chunk, reply_markup=markup, parse_mode=None)
                except Exception:
                    pass

# ---------------------------------------------------------------------------
# Command Handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command with rich dashboard menu."""
    text = (
        "🏆 *SELAMAT DATANG DI SBOBET AI MATCH & PARLAY SUITE* 🏆\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Asisten pintar analisis sepak bola & pasaran SBOBET bertenaga **Google Gemini AI & Model Kuantitatif Poisson xG**.\n\n"
        "✨ *Cara Menggunakan (Paling Praktis):*\n"
        "1️⃣ *Ketik Nama Tim Saja:*\n"
        "`Arsenal vs Chelsea` atau `Madrid vs Barca`\n\n"
        "2️⃣ *Kirim Multi-Laga Sekaligus:*\n"
        "`1. Arsenal vs Chelsea`\n"
        "`2. Real Madrid vs Barcelona`\n"
        "`3. Inter Milan vs Juventus`\n"
        "_(Bot otomatis membedah seluruh laga, memilihkan Top 8 pasaran SBOBET terbaik, dan meracik tiket Mix Parlay)_\n\n"
        "3️⃣ *Kirim Foto Screenshot / File PDF Slip:* Bot langsung membaca seluruh laga!\n"
        "4️⃣ *Pilih 1-Klik dari Jadwal Real-Time Hari Ini!*"
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
    """Handle /menu command."""
    text = "📋 *DASHBOARD MENU UTAMA*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nSilakan pilih menu:"
    await safe_reply(update, text, reply_markup=get_main_menu_keyboard())


async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /schedule command with real-time live match feed."""
    status_msg = None
    if update.message:
        status_msg = await update.message.reply_text("⏳ *Memuat jadwal pertandingan real-time dari soccervital.com...*", parse_mode="Markdown")
    try:
        today_list = await live_feed.fetch_today_schedule()
        text, markup = format_live_schedule_view(today_list, "today")
        if status_msg:
            try:
                await status_msg.delete()
            except Exception:
                pass
        await safe_reply(update, text, reply_markup=markup)
    except Exception as e:
        if status_msg:
            try:
                await status_msg.delete()
            except Exception:
                pass
        await safe_reply(update, f"❌ Gagal memuat jadwal: {e}")


async def cmd_tracker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /tracker command."""
    chat_id = update.effective_chat.id
    text, markup = format_tracker_dashboard(chat_id)
    await safe_reply(update, text, reply_markup=markup)


async def cmd_bankroll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /bankroll command."""
    chat_id = update.effective_chat.id
    args = context.args if context else []
    if args:
        raw_arg = " ".join(args)
        amount = parse_currency_amount(raw_arg)
        if amount:
            saved = tracker.set_user_bankroll(chat_id, amount)
            await safe_reply(
                update,
                f"✅ *Bankroll berhasil diatur menjadi:* `{_format_rupiah(saved)}`\n"
                "Seluruh rekomendasi alokasi staking Kelly pada analisis laga berikutnya akan otomatis menyesuaikan.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

    text, markup = format_bankroll_view(chat_id)
    await safe_reply(update, text, reply_markup=markup)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command with detailed manual."""
    text = (
        "📖 *PANDUAN LENGKAP PENGGUNAAN BOT*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 *1. Cara Menganalisis Pertandingan:*\n"
        "• Cukup ketik nama tim: `Arsenal vs Chelsea`\n"
        "• Atau kirim daftar banyak laga sekaligus:\n"
        "  `Arsenal vs Chelsea`\n"
        "  `Real Madrid vs Barcelona`\n"
        "  `Inter vs Juventus`\n"
        "• Atau kirim **foto screenshot / file PDF** slip taruhan kamu.\n\n"
        "📌 *2. Pasaran SBOBET yang Dianalisis:*\n"
        "• 🚩 *Asian Handicap (HDP):* Tim pemegang voor & proyeksi kei wajar.\n"
        "• ⚽ *Over / Under (O/U):* Prediksi total gol (2.5 / 2.75 / 3.0).\n"
        "• 🤝 *BTTS:* Peluang kedua tim saling mencetak gol (Yes/No).\n"
        "• 👑 *1X2:* Peluang menang murni Home / Draw / Away.\n\n"
        "📌 *3. Pemantau Slip & Notifikasi Live:*\n"
        "Setelah melihat laporan analisis, klik tombol **`💾 Simpan Tiket`**. "
        "Bot akan otomatis memantau pertandingan kamu di latar belakang dan mengirimkan **notifikasi jika terjadi gol atau laga selesai (FT)**!"
    )
    back_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu_main")]]
    )
    await safe_reply(update, text, reply_markup=back_kb)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command showing system diagnostics."""
async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pause/Turn OFF bot directly from Telegram."""
    global _BOT_ACTIVE_STATE
    _BOT_ACTIVE_STATE = False
    await safe_reply(
        update,
        "🔴 *BOT DINONAKTIFKAN (MODE TIDUR / OFF)*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Bot sekarang dalam mode jeda dan tidak akan memproses analisa pertandingan.\n\n"
        "👉 Ketik **/on** atau **/resume** kapan saja untuk menyalakan kembali bot.",
    )


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resume/Turn ON bot directly from Telegram."""
    global _BOT_ACTIVE_STATE
    _BOT_ACTIVE_STATE = True
    await safe_reply(
        update,
        "🟢 *BOT TELAH MENYALA KEMBALI (ACTIVE / ON)*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Bot siap melayani analisis pertandingan, jadwal, dan pemantau skor live!",
        reply_markup=get_main_menu_keyboard(),
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command showing system diagnostics."""
    active_slips = tracker.get_active_slips_all_users()
    state_str = "🟢 AKTIF / ON" if _BOT_ACTIVE_STATE else "🔴 PAUSE / OFF"
    text = (
        "⚡ *STATUS SISTEM BOT 24/7* ⚡\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• 🔌 *Power Switch:* {state_str}\n"
        f"• 🤖 *AI Engine:* 🟢 Google Gemini ({settings.gemini_model}) - 100% Gratis\n"
        f"• 🌐 *Live Match Feed:* 🟢 soccervital.com (Terhubung)\n"
        f"• 🛰️ *Pemantau Slip Live:* 🟢 Aktif ({len(active_slips)} tiket dipantau)\n"
        f"• 🌐 *Cloud Health Server:* Port `{settings.port}` (Aktif)\n\n"
        "Gunakan **/off** untuk mematikan bot atau **/on** untuk menyalakan langsung dari HP."
    )
    back_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu_main")]]
    )
    await safe_reply(update, text, reply_markup=back_kb)
# ---------------------------------------------------------------------------
# Ingestion & Analysis Execution Flow
# ---------------------------------------------------------------------------

async def run_execution_flow(
    update: Update,
    matches: list[ExtractedMatch],
    existing_status_msg=None,
):
    """Execute SBOBET analysis pipeline and render output."""
    if not matches:
        return

    chat_id = update.effective_chat.id
    target_msg = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    status_msg = existing_status_msg

    if not status_msg and target_msg:
        status_msg = await target_msg.reply_text(
            f"⏳ *Memproses analisis mendalam untuk {len(matches)} laga...*\n"
            f"• Menghitung Poisson xG & Proyeksi Skor...\n"
            f"• Memilih pasaran terbaik SBOBET (HDP, O/U, BTTS)...",
            parse_mode="Markdown",
        )

    try:
        if len(matches) == 1:
            # Single Match Analysis
            analysis = sbobet_engine.analyze_match_pipeline(matches[0])
            _ACTIVE_ANALYSES[chat_id] = ("single", analysis)

            if status_msg:
                try:
                    await status_msg.delete()
                except Exception:
                    pass

            text, markup = format_single_match_analysis(analysis, user_id=chat_id)
            await safe_reply(update, text, reply_markup=markup)

        else:
            # Multi-Match Mix Parlay & Top 8 Analysis
            parlay = sbobet_engine.analyze_parlay_pipeline(matches)
            _ACTIVE_ANALYSES[chat_id] = ("parlay", parlay)

            if status_msg:
                try:
                    await status_msg.delete()
                except Exception:
                    pass

            text, markup = format_parlay_analysis(parlay, user_id=chat_id)
            await safe_reply(update, text, reply_markup=markup)

    except Exception as e:
        logger.exception("Analysis execution error")
        if status_msg:
            try:
                await status_msg.delete()
            except Exception:
                pass
        await safe_reply(update, f"❌ Terjadi kesalahan saat menganalisis: {e}", parse_mode=None)


# ---------------------------------------------------------------------------
# Message & Document Handlers
# ---------------------------------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _BOT_ACTIVE_STATE
    text = update.message.text.strip()
    if not text:
        return

    if text.lower() in ("/on", "/resume", "nyalakan", "on"):
        await cmd_resume(update, context)
        return
    elif text.lower() in ("/off", "/pause", "matikan", "off"):
        await cmd_pause(update, context)
        return

    if not _BOT_ACTIVE_STATE:
        await update.message.reply_text("💤 *Bot sedang dimatikan (Mode Tidur).*\nKetik **/on** untuk menyalakan kembali.", parse_mode="Markdown")
        return

    # Check Reply Keyboard Buttons
    if text in ("📅 Jadwal Laga (Hari Ini / Besok)", "/schedule"):
        await cmd_schedule(update, context)
        return
    elif text in ("📈 Bet Tracker & Live Skor", "/tracker"):
        await cmd_tracker(update, context)
        return
    elif text in ("💵 Atur Modal (Bankroll)", "/bankroll"):
        await cmd_bankroll(update, context)
        return
    elif text in ("📖 Panduan & Cara Pakai", "/help"):
        await cmd_help(update, context)
        return

    # Check if user typed a currency amount to update bankroll (e.g. "40.000", "50k", "Rp 500.000", "1.5jt")
    bankroll_amount = parse_currency_amount(text)
    if bankroll_amount:
        saved = tracker.set_user_bankroll(update.effective_chat.id, bankroll_amount)
        await update.message.reply_text(
            f"✅ *Bankroll berhasil diatur menjadi:* `{_format_rupiah(saved)}`\n"
            "Seluruh rekomendasi nominal pasang Rupiah di tiket parlay dan single akan otomatis dihitung berdasarkan modal ini.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="Markdown",
        )
        return
    # Extract matches via Universal Gemini Router
    status_msg = await update.message.reply_text("🔍 *Membaca pertandingan via AI...*", parse_mode="Markdown")
    try:
        matches = await gemini_extractor.extract_matches_from_text(text)
        if not matches:
            await status_msg.edit_text(
                "❌ *Tidak ada pertandingan yang terdeteksi.*\n\n"
                "Silakan ketik nama tim seperti:\n"
                "`Arsenal vs Chelsea`\n"
                "`Real Madrid vs Barcelona`\n\n"
                "Atau pilih dari tombol **📅 Jadwal Laga** di bawah.",
                reply_markup=get_main_menu_keyboard(),
                parse_mode="Markdown",
            )
            return

        await run_execution_flow(update, matches, existing_status_msg=status_msg)

    except Exception as e:
        logger.exception("Text parsing error")
        try:
            await status_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(f"❌ Gagal memproses teks: {e}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming screenshot photos using Gemini Vision."""
    status_msg = await update.message.reply_text("🔍 *Membaca screenshot pertandingan via Gemini Vision...*", parse_mode="Markdown")

    try:
        photo = update.message.photo[-1]
        tg_file = await context.bot.get_file(photo.file_id)
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        image_bytes = buf.getvalue()

        matches = await gemini_extractor.extract_matches_from_image(image_bytes)

        if not matches:
            await status_msg.edit_text(
                "❌ Gambar terbaca, namun tidak ada nama tim pertandingan yang terdeteksi.\n"
                "Pastikan gambar menampilkan nama tim dengan jelas, atau ketik manual.",
                reply_markup=get_main_menu_keyboard(),
                parse_mode="Markdown",
            )
            return

        await run_execution_flow(update, matches, existing_status_msg=status_msg)

    except Exception as e:
        logger.exception("Photo parsing error")
        try:
            await status_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(f"❌ Gagal memproses gambar: {e}", reply_markup=get_main_menu_keyboard())


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming PDF documents containing multiple matches."""
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
            "Silakan kirim file **PDF (.pdf)** atau foto screenshot langsung.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="Markdown",
        )
        return

    status_msg = await update.message.reply_text(
        f"📄 *Menerima dokumen:* `{filename}`\n"
        f"⏳ Mengunduh dan mengekstrak seluruh pertandingan via AI...",
        parse_mode="Markdown",
    )

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        file_bytes = buf.getvalue()

        if is_pdf:
            matches, total_pages = await gemini_extractor.extract_matches_from_pdf(file_bytes)
        else:
            matches = await gemini_extractor.extract_matches_from_image(file_bytes)

        if not matches:
            await status_msg.edit_text(
                f"❌ Dokumen `{filename}` terbaca, namun tidak ada pertandingan yang terdeteksi.\n"
                "Pastikan isi file menampilkan nama tim pertandingan dengan jelas.",
                reply_markup=get_main_menu_keyboard(),
                parse_mode="Markdown",
            )
            return

        await run_execution_flow(update, matches, existing_status_msg=status_msg)

    except Exception as e:
        logger.exception("Document parsing error")
        try:
            await status_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(f"❌ Gagal memproses dokumen `{filename}`: {e}", reply_markup=get_main_menu_keyboard())


# ---------------------------------------------------------------------------
# Callback Query Navigation Handler
# ---------------------------------------------------------------------------

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle interactive inline buttons across all features."""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

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

    # 2. Schedule Navigation (Tabs: Today / Tomorrow)
    elif data in ("menu_schedule", "sched_tab_today"):
        today_list = await live_feed.fetch_today_schedule()
        text, markup = format_live_schedule_view(today_list, "today")
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            await safe_reply(update, text, reply_markup=markup)
        return

    elif data == "sched_tab_tomorrow":
        tom_list = await live_feed.fetch_tomorrow_schedule()
        text, markup = format_live_schedule_view(tom_list, "tomorrow")
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            await safe_reply(update, text, reply_markup=markup)
        return

    elif data.startswith("sched_match_"):
        match_id = data.replace("sched_match_", "")
        today_list = await live_feed.fetch_today_schedule()
        tom_list = await live_feed.fetch_tomorrow_schedule()
        target_m = None
        for m in today_list + tom_list:
            if m["id"] == match_id:
                target_m = m
                break

        if target_m:
            match_obj = ExtractedMatch(home=target_m["home"], away=target_m["away"], league=target_m.get("league", ""))
            await run_execution_flow(update, [match_obj])
        return

    elif data in ("sched_parlay_today", "sched_parlay_tomorrow"):
        is_tom = "tomorrow" in data
        match_list = await live_feed.fetch_tomorrow_schedule() if is_tom else await live_feed.fetch_today_schedule()
        if match_list:
            top_matches = [
                ExtractedMatch(home=m["home"], away=m["away"], league=m.get("league", ""))
                for m in match_list[:4]  # take top 4 matches
            ]
            await run_execution_flow(update, top_matches)
        return

    # 3. Bet Tracker & Live Score Monitoring
    elif data == "menu_tracker":
        text, markup = format_tracker_dashboard(chat_id)
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            await safe_reply(update, text, reply_markup=markup)
        return

    elif data == "track_save_single_0":
        sess = _ACTIVE_ANALYSES.get(chat_id)
        if not sess or sess[0] != "single":
            await query.answer("⚠️ Data analisis tidak ditemukan.", show_alert=True)
            return

        analysis: DeepMatchAnalysis = sess[1]
        bankroll = tracker.get_user_bankroll(chat_id)
        stake_rp = bankroll * analysis.recommended_stake_pct
        title = f"Single: {analysis.match.clean_title()}"
        matches_payload = [
            {
                "home": analysis.match.home,
                "away": analysis.match.away,
                "pick": analysis.best_sbobet_pick.selection,
                "odds": analysis.best_sbobet_pick.projected_odds,
            }
        ]

        slip_id = tracker.save_slip(
            user_id=chat_id,
            slip_title=title,
            matches_data=matches_payload,
            total_odds=analysis.best_sbobet_pick.projected_odds,
            stake_amount=stake_rp,
        )
        await query.answer(f"✅ Tiket #{slip_id} disimpan! Bot memantau linimasa skor langsung...", show_alert=True)
        text, markup = format_tracker_dashboard(chat_id)
        await safe_reply(update, text, reply_markup=markup)
        return

    elif data == "track_save_parlay":
        sess = _ACTIVE_ANALYSES.get(chat_id)
        if not sess or sess[0] != "parlay":
            await query.answer("⚠️ Data tiket parlay tidak ditemukan.", show_alert=True)
            return

        parlay: ParlayAnalysisReport = sess[1]
        bankroll = tracker.get_user_bankroll(chat_id)
        stake_rp = bankroll * parlay.recommended_kelly_stake
        title = f"Mix Parlay SBOBET ({len(parlay.matches)} Laga)"
        matches_payload = [
            {
                "home": m.match.home,
                "away": m.match.away,
                "pick": m.best_sbobet_pick.selection,
                "odds": m.best_sbobet_pick.projected_odds,
            }
            for m in parlay.matches
        ]

        slip_id = tracker.save_slip(
            user_id=chat_id,
            slip_title=title,
            matches_data=matches_payload,
            total_odds=parlay.combined_odds,
            stake_amount=stake_rp,
        )
        await query.answer(f"✅ Mix Parlay #{slip_id} disimpan! Pemantau skor live aktif 🛰️", show_alert=True)
        text, markup = format_tracker_dashboard(chat_id)
        await safe_reply(update, text, reply_markup=markup)
        return

    elif data.startswith("settle_"):
        parts = data.split("_")
        slip_id = int(parts[1])
        res = parts[2]
        tracker.settle_slip(slip_id, chat_id, res)
        await query.answer(f"✅ Tiket #{slip_id} diselesaikan sebagai {res}!", show_alert=True)
        text, markup = format_tracker_dashboard(chat_id)
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            await safe_reply(update, text, reply_markup=markup)
        return

    # 4. Bankroll Management
    elif data == "menu_bankroll":
        text, markup = format_bankroll_view(chat_id)
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
            "Seluruh rekomendasi nominal pasang Rupiah di tiket berikutnya akan otomatis dihitung berdasarkan modal ini."
        )
        await safe_reply(update, text, reply_markup=get_main_menu_keyboard())
        return

    # 5. Help, Status
    elif data == "menu_help":
        await cmd_help(update, context)
        return
    elif data == "menu_status":
        await cmd_status(update, context)
        return

    # 6. Match Drilldown in Parlay
    elif data.startswith("drill_match_"):
        sess = _ACTIVE_ANALYSES.get(chat_id)
        if sess and sess[0] == "parlay":
            parlay: ParlayAnalysisReport = sess[1]
            idx = int(data.replace("drill_match_", ""))
            if 0 <= idx < len(parlay.matches):
                match_analysis = parlay.matches[idx]
                text, markup = format_single_match_analysis(match_analysis, user_id=chat_id)
                try:
                    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
                except Exception:
                    await safe_reply(update, text, reply_markup=markup)
        return


# ---------------------------------------------------------------------------
# 24/7 Cloud HTTP Health Server
# ---------------------------------------------------------------------------

async def _http_client_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Handle health check HTTP requests for 24/7 cloud hosting."""
    try:
        await reader.readline()
        while True:
            line = await reader.readline()
            if not line or line in (b"\r\n", b"\n"):
                break

        body = json.dumps(
            {
                "status": "healthy",
                "service": "SBOBET AI Match & Parlay Suite",
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
    """Start non-blocking HTTP server on configured port."""
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
    """Main entrypoint initializing Telegram Bot, SQLite DB, and Live Monitor Worker."""
    if not settings.has_telegram:
        print("\n❌ ERROR: TELEGRAM_BOT_TOKEN belum disetel di file .env!")
        return

    logger.info("Memulai SBOBET AI Match & Parlay Suite with Live Slip Monitor...")

    # 1. Initialize SQLite Database
    tracker.init_db()

    # 2. Start HTTP Health Server in background
    http_server = await start_http_server()

    # 3. Build Telegram Application
    app = Application.builder().token(settings.telegram_bot_token).build()

    # Set up Telegram native menu commands list
    try:
        commands = [
            BotCommand("start", "Mulai & Buka Dashboard Utama"),
            BotCommand("menu", "Tampilkan Menu Pilihan Fitur"),
            BotCommand("schedule", "📅 Jadwal Laga (Hari Ini & Besok)"),
            BotCommand("tracker", "📈 Bet Tracker & Live Score Monitor"),
            BotCommand("bankroll", "💵 Atur Modal & Staking Rp"),
            BotCommand("help", "📖 Panduan Penggunaan"),
            BotCommand("status", "📊 Cek Status Server"),
        ]
        await app.bot.set_my_commands(commands)
        logger.info("✅ Telegram Bot Commands Menu berhasil didaftarkan.")
    except Exception as e:
        logger.warning(f"Could not register Telegram commands: {e}")

    # Register Handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("schedule", cmd_schedule))
    app.add_handler(CommandHandler("tracker", cmd_tracker))
    app.add_handler(CommandHandler("bankroll", cmd_bankroll))
    app.add_handler(CommandHandler("on", cmd_resume))
    app.add_handler(CommandHandler("off", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # 4. Start Live Monitor Background Task & Polling
    async with app:
        await app.start()
        monitor_task = asyncio.create_task(start_live_monitor_worker(app.bot))

        await app.updater.start_polling()
        logger.info("✅ SBOBET AI Bot berhasil tersambung dan siap melayani 24/7.")

        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Bot dihentikan.")
        finally:
            monitor_task.cancel()
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
