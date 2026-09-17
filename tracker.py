"""
tracker.py — Persistent SQLite Storage for User Bankroll, Bet Slips, and Live Match Tracking.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from models import TrackedSlip, UserStats

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parley_data.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize SQLite tables for user bankroll settings and slip tracking."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_bankroll (
                user_id INTEGER PRIMARY KEY,
                bankroll REAL DEFAULT 1000000.0,
                currency TEXT DEFAULT 'IDR',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tracked_slips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                slip_title TEXT NOT NULL,
                matches_json TEXT NOT NULL,
                total_odds REAL NOT NULL,
                stake_amount REAL NOT NULL,
                potential_return REAL NOT NULL,
                status TEXT DEFAULT 'PENDING',
                live_status_summary TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                settled_at TEXT DEFAULT '',
                profit_loss REAL DEFAULT 0.0
            )
            """
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Bankroll Management
# ---------------------------------------------------------------------------

def get_user_bankroll(user_id: int) -> float:
    """Get user bankroll in IDR. Defaults to Rp 1.000.000."""
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT bankroll FROM user_bankroll WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            return float(row["bankroll"])
        conn.execute("INSERT OR IGNORE INTO user_bankroll (user_id, bankroll) VALUES (?, 1000000.0)", (user_id,))
        conn.commit()
        return 1000000.0


def set_user_bankroll(user_id: int, amount: float) -> float:
    """Set or update user bankroll."""
    init_db()
    clean = max(10000.0, float(amount))
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO user_bankroll (user_id, bankroll, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET bankroll = excluded.bankroll, updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, clean),
        )
        conn.commit()
    return clean


# ---------------------------------------------------------------------------
# Slip Tracking & Live Status
# ---------------------------------------------------------------------------

def save_slip(
    user_id: int,
    slip_title: str,
    matches_data: list[dict],
    total_odds: float,
    stake_amount: float,
) -> int:
    """Save an analyzed slip into the persistent tracker database."""
    init_db()
    now_str = datetime.now().strftime("%d-%m-%Y %H:%M")
    pot_return = round(stake_amount * total_odds, 2)
    matches_json_str = json.dumps(matches_data)

    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO tracked_slips (
                user_id, slip_title, matches_json, total_odds, stake_amount,
                potential_return, status, live_status_summary, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', 'Menunggu Kickoff ⏳', ?)
            """,
            (user_id, slip_title, matches_json_str, total_odds, stake_amount, pot_return, now_str),
        )
        conn.commit()
        return cur.lastrowid


def get_user_slips(user_id: int, limit: int = 10, status: str | None = None) -> list[TrackedSlip]:
    """Retrieve tracked slips for a user."""
    init_db()
    query = "SELECT * FROM tracked_slips WHERE user_id = ?"
    params: list = [user_id]

    if status:
        query += " AND status = ?"
        params.append(status.upper())

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        slips: list[TrackedSlip] = []
        for r in rows:
            slips.append(
                TrackedSlip(
                    id=r["id"],
                    user_id=r["user_id"],
                    slip_title=r["slip_title"],
                    matches_json=r["matches_json"],
                    total_odds=r["total_odds"],
                    stake_amount=r["stake_amount"],
                    potential_return=r["potential_return"],
                    status=r["status"],
                    live_status_summary=r["live_status_summary"] or "",
                    created_at=r["created_at"],
                    settled_at=r["settled_at"] or "",
                    profit_loss=r["profit_loss"],
                )
            )
        return slips


def get_active_slips_all_users() -> list[TrackedSlip]:
    """Retrieve all pending or live slips across all users for the background live monitor."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tracked_slips WHERE status IN ('PENDING', 'LIVE') ORDER BY id ASC"
        ).fetchall()
        slips: list[TrackedSlip] = []
        for r in rows:
            slips.append(
                TrackedSlip(
                    id=r["id"],
                    user_id=r["user_id"],
                    slip_title=r["slip_title"],
                    matches_json=r["matches_json"],
                    total_odds=r["total_odds"],
                    stake_amount=r["stake_amount"],
                    potential_return=r["potential_return"],
                    status=r["status"],
                    live_status_summary=r["live_status_summary"] or "",
                    created_at=r["created_at"],
                    settled_at=r["settled_at"] or "",
                    profit_loss=r["profit_loss"],
                )
            )
        return slips


def update_slip_live_status(slip_id: int, live_summary: str, status: str = "LIVE"):
    """Update live score summary on a tracked slip."""
    init_db()
    with get_connection() as conn:
        conn.execute(
            "UPDATE tracked_slips SET live_status_summary = ?, status = ? WHERE id = ?",
            (live_summary, status, slip_id),
        )
        conn.commit()


def settle_slip(slip_id: int, user_id: int, result: str) -> bool:
    """Settle a slip with 'WIN', 'LOSE', or 'VOID'."""
    init_db()
    clean_res = result.upper()
    if clean_res not in ("WIN", "LOSE", "VOID"):
        return False

    now_str = datetime.now().strftime("%d-%m-%Y %H:%M")

    with get_connection() as conn:
        row = conn.execute(
            "SELECT stake_amount, potential_return FROM tracked_slips WHERE id = ? AND user_id = ?",
            (slip_id, user_id),
        ).fetchone()

        if not row:
            return False

        stake = float(row["stake_amount"])
        pot_return = float(row["potential_return"])

        if clean_res == "WIN":
            profit_loss = round(pot_return - stake, 2)
            summary = f"SELESAI: WIN (Profit +Rp {int(profit_loss):,}) ✅".replace(",", ".")
        elif clean_res == "LOSE":
            profit_loss = -round(stake, 2)
            summary = f"SELESAI: LOSE (-Rp {int(stake):,}) ❌".replace(",", ".")
        else:
            profit_loss = 0.0
            summary = "SELESAI: VOID / REFUND 🔄"

        conn.execute(
            """
            UPDATE tracked_slips
            SET status = ?, profit_loss = ?, settled_at = ?, live_status_summary = ?
            WHERE id = ? AND user_id = ?
            """,
            (clean_res, profit_loss, now_str, summary, slip_id, user_id),
        )
        conn.commit()
        return True


def delete_slip(slip_id: int, user_id: int) -> bool:
    """Delete a tracked slip."""
    init_db()
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM tracked_slips WHERE id = ? AND user_id = ?", (slip_id, user_id))
        conn.commit()
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Statistics & Win Rate Analytics
# ---------------------------------------------------------------------------

def get_user_stats(user_id: int) -> UserStats:
    """Calculate aggregate win rate, profit/loss, ROI, and streak."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT status, stake_amount, profit_loss FROM tracked_slips WHERE user_id = ? ORDER BY id ASC",
            (user_id,),
        ).fetchall()

    if not rows:
        return UserStats()

    total_bets = len(rows)
    wins = sum(1 for r in rows if r["status"] == "WIN")
    losses = sum(1 for r in rows if r["status"] == "LOSE")
    voids = sum(1 for r in rows if r["status"] == "VOID")
    pending = sum(1 for r in rows if r["status"] in ("PENDING", "LIVE"))

    total_staked = sum(float(r["stake_amount"]) for r in rows if r["status"] in ("WIN", "LOSE", "VOID"))
    net_profit = sum(float(r["profit_loss"]) for r in rows if r["status"] in ("WIN", "LOSE", "VOID"))
    total_return = total_staked + net_profit

    settled_count = wins + losses
    win_rate = (wins / settled_count * 100) if settled_count > 0 else 0.0
    roi = (net_profit / total_staked * 100) if total_staked > 0 else 0.0

    streak_type = ""
    streak_count = 0
    for r in reversed(rows):
        st = r["status"]
        if st not in ("WIN", "LOSE"):
            continue
        if not streak_type:
            streak_type = st
            streak_count = 1
        elif streak_type == st:
            streak_count += 1
        else:
            break

    if streak_type == "WIN":
        streak_str = f"🔥 {streak_count}W Menang Beruntun"
    elif streak_type == "LOSE":
        streak_str = f"❄️ {streak_count}L Kalah Beruntun"
    else:
        streak_str = "0 (Baru)"

    return UserStats(
        total_bets=total_bets,
        wins=wins,
        losses=losses,
        voids=voids,
        pending=pending,
        total_staked=total_staked,
        total_return=total_return,
        net_profit=net_profit,
        win_rate_pct=round(win_rate, 1),
        roi_pct=round(roi, 1),
        current_streak=streak_str,
    )
