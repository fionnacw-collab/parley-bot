"""
live_monitor.py — Background Real-Time Slip Monitor & Goal Timeline Notifier.
Periodically checks live match scoreboards, notifies users on goal events / HT / FT,
and automatically settles bets in the SQLite tracker.
"""

from __future__ import annotations

import asyncio
import json
import logging
from telegram import Bot
import live_feed
import tracker

logger = logging.getLogger(__name__)

# Track last known score per slip to avoid duplicate notification alerts: slip_id -> score_string
_LAST_NOTIFIED_SCORES: dict[int, str] = {}


async def check_slips_once(bot: Bot):
    """Perform one monitoring cycle across all active tracked slips."""
    active_slips = tracker.get_active_slips_all_users()
    if not active_slips:
        return

    live_scores = await live_feed.fetch_live_scores()
    if not live_scores:
        return

    for slip in active_slips:
        try:
            matches = json.loads(slip.matches_json)
        except Exception:
            continue

        updated_summaries: list[str] = []
        has_live_update = False
        all_finished = True

        for m in matches:
            home = m.get("home", "")
            away = m.get("away", "")
            pick = m.get("pick", "")
            key = f"{home.lower().strip()} vs {away.lower().strip()}"

            score_info = live_scores.get(key)
            if score_info:
                has_live_update = True
                status_m = score_info.get("status", "LIVE")
                h_s = score_info.get("home_score", 0)
                a_s = score_info.get("away_score", 0)
                score_str = f"{home} {h_s}-{a_s} {away} ({status_m})"
                updated_summaries.append(score_str)

                if status_m != "FT":
                    all_finished = False
            else:
                updated_summaries.append(f"{home} vs {away} (Menunggu)")
                all_finished = False

        if has_live_update and updated_summaries:
            current_summary = " | ".join(updated_summaries)
            last_summary = _LAST_NOTIFIED_SCORES.get(slip.id, "")

            # If score or status changed, notify the user via Telegram
            if current_summary != last_summary:
                _LAST_NOTIFIED_SCORES[slip.id] = current_summary
                tracker.update_slip_live_status(slip.id, current_summary, "LIVE")

                try:
                    notif_text = (
                        f"🔔 *UPDATE LINIMASA PERTANDINGAN [TIKET #{slip.id}]* 🔔\n"
                        f"📋 *{slip.slip_title}* (@`{slip.total_odds:.2f}`)\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    )
                    for summ in updated_summaries:
                        notif_text += f"⚽ `{summ}`\n"

                    notif_text += (
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"💰 Modal: `Rp {int(slip.stake_amount):,}` | Potensi: `Rp {int(slip.potential_return):,}`\n"
                        "Bot memantau pertandingan kamu secara real-time..."
                    ).replace(",", ".")

                    await bot.send_message(
                        chat_id=slip.user_id,
                        text=notif_text,
                        parse_mode="Markdown",
                    )
                except Exception as send_err:
                    logger.debug(f"Could not send live notification to {slip.user_id}: {send_err}")


async def start_live_monitor_worker(bot: Bot, interval_seconds: int = 90):
    """Indefinite background worker monitoring live slips."""
    logger.info("🛰️ Live Slip Monitor & Notification Worker aktif di latar belakang.")
    while True:
        try:
            await check_slips_once(bot)
        except Exception as e:
            logger.debug(f"Live monitor cycle error: {e}")
        await asyncio.sleep(interval_seconds)
