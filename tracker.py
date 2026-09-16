"""
tracker.py — Persistent SQLite storage for User Bankroll, Bet Tracking, and Win-Rate Analytics.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from models import TrackedBet, UserStats

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parley_data.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables for user settings and bet tracker."""
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
            CREATE TABLE IF NOT EXISTS tracked_bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                ticket_title TEXT NOT NULL,
                legs_summary TEXT NOT NULL,
                odds REAL NOT NULL,
                stake_amount REAL NOT NULL,
                potential_return REAL NOT NULL,
                status TEXT DEFAULT 'PENDING',
                profit_loss REAL DEFAULT 0.0,
                created_at TEXT NOT NULL,
                settled_at TEXT DEFAULT ''
            )
            """
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Bankroll Management
# ---------------------------------------------------------------------------

def get_user_bankroll(user_id: int) -> float:
    """Retrieve user bankroll in Rupiah. Defaults to Rp 1.000.000."""
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT bankroll FROM user_bankroll WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row:
            return float(row["bankroll"])
        # Insert default 1,000,000 IDR
        conn.execute(
            "INSERT OR IGNORE INTO user_bankroll (user_id, bankroll) VALUES (?, 1000000.0)",
            (user_id,),
        )
        conn.commit()
        return 1000000.0


def set_user_bankroll(user_id: int, amount: float) -> float:
    """Set or update user bankroll in Rupiah."""
    init_db()
    clean_amount = max(10000.0, float(amount))  # Minimum Rp 10.000
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO user_bankroll (user_id, bankroll, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                bankroll = excluded.bankroll,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, clean_amount),
        )
        conn.commit()
    return clean_amount


# ---------------------------------------------------------------------------
# Bet Tracking & Settlement
# ---------------------------------------------------------------------------

def save_bet(
    user_id: int,
    ticket_title: str,
    legs_summary: str,
    odds: float,
    stake_amount: float,
) -> int:
    """Save an analyzed bet ticket into the tracker database."""
    init_db()
    now_str = datetime.now().strftime("%d-%m-%Y %H:%M")
    potential_return = round(stake_amount * odds, 2)

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tracked_bets (
                user_id, ticket_title, legs_summary, odds, stake_amount,
                potential_return, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)
            """,
            (user_id, ticket_title, legs_summary, odds, stake_amount, potential_return, now_str),
        )
        conn.commit()
        return cursor.lastrowid


def settle_bet(bet_id: int, user_id: int, result: str) -> bool:
    """
    Settle a bet with 'WIN', 'LOSE', or 'VOID'.
    Updates profit/loss and settled_at timestamp.
    """
    init_db()
    clean_res = result.upper()
    if clean_res not in ("WIN", "LOSE", "VOID"):
        return False

    now_str = datetime.now().strftime("%d-%m-%Y %H:%M")

    with get_connection() as conn:
        row = conn.execute(
            "SELECT stake_amount, potential_return FROM tracked_bets WHERE id = ? AND user_id = ?",
            (bet_id, user_id),
        ).fetchone()

        if not row:
            return False

        stake = float(row["stake_amount"])
        pot_return = float(row["potential_return"])

        if clean_res == "WIN":
            profit_loss = round(pot_return - stake, 2)
        elif clean_res == "LOSE":
            profit_loss = -round(stake, 2)
        else:  # VOID
            profit_loss = 0.0

        conn.execute(
            """
            UPDATE tracked_bets
            SET status = ?, profit_loss = ?, settled_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (clean_res, profit_loss, now_str, bet_id, user_id),
        )
        conn.commit()
        return True


def get_user_bets(user_id: int, limit: int = 10, status: str | None = None) -> list[TrackedBet]:
    """Retrieve user bets from history."""
    init_db()
    query = "SELECT * FROM tracked_bets WHERE user_id = ?"
    params: list = [user_id]

    if status:
        query += " AND status = ?"
        params.append(status.upper())

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        bets: list[TrackedBet] = []
        for r in rows:
            bets.append(
                TrackedBet(
                    id=r["id"],
                    user_id=r["user_id"],
                    ticket_title=r["ticket_title"],
                    legs_summary=r["legs_summary"],
                    odds=r["odds"],
                    stake_amount=r["stake_amount"],
                    potential_return=r["potential_return"],
                    status=r["status"],
                    created_at=r["created_at"],
                    settled_at=r["settled_at"] or "",
                    profit_loss=r["profit_loss"],
                )
            )
        return bets


def get_bet_by_id(bet_id: int, user_id: int) -> TrackedBet | None:
    """Get single bet by ID."""
    init_db()
    with get_connection() as conn:
        r = conn.execute(
            "SELECT * FROM tracked_bets WHERE id = ? AND user_id = ?",
            (bet_id, user_id),
        ).fetchone()
        if not r:
            return None
        return TrackedBet(
            id=r["id"],
            user_id=r["user_id"],
            ticket_title=r["ticket_title"],
            legs_summary=r["legs_summary"],
            odds=r["odds"],
            stake_amount=r["stake_amount"],
            potential_return=r["potential_return"],
            status=r["status"],
            created_at=r["created_at"],
            settled_at=r["settled_at"] or "",
            profit_loss=r["profit_loss"],
        )


def delete_bet(bet_id: int, user_id: int) -> bool:
    """Delete a tracked bet."""
    init_db()
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM tracked_bets WHERE id = ? AND user_id = ?",
            (bet_id, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Statistics & Win Rate Analytics
# ---------------------------------------------------------------------------

def get_user_stats(user_id: int) -> UserStats:
    """Calculate aggregate win rate, profit/loss, ROI, and streak."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT status, stake_amount, profit_loss FROM tracked_bets WHERE user_id = ? ORDER BY id ASC",
            (user_id,),
        ).fetchall()

    if not rows:
        return UserStats()

    total_bets = len(rows)
    wins = sum(1 for r in rows if r["status"] == "WIN")
    losses = sum(1 for r in rows if r["status"] == "LOSE")
    voids = sum(1 for r in rows if r["status"] == "VOID")
    pending = sum(1 for r in rows if r["status"] == "PENDING")

    total_staked = sum(float(r["stake_amount"]) for r in rows if r["status"] in ("WIN", "LOSE", "VOID"))
    net_profit = sum(float(r["profit_loss"]) for r in rows if r["status"] in ("WIN", "LOSE", "VOID"))
    total_return = total_staked + net_profit

    settled_count = wins + losses
    win_rate = (wins / settled_count * 100) if settled_count > 0 else 0.0
    roi = (net_profit / total_staked * 100) if total_staked > 0 else 0.0

    # Calculate current win/loss streak
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
