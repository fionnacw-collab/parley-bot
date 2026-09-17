"""
config.py — Centralized configuration loader for SBOBET AI Match & Parlay Suite.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    # Web & Hosting
    port: int = int(os.getenv("PORT", "8080"))
    host: str = os.getenv("HOST", "0.0.0.0")

    # Staking & Risk defaults
    default_kelly_fraction: float = float(os.getenv("KELLY_FRACTION", "0.25"))

    @property
    def has_telegram(self) -> bool:
        return bool(self.telegram_bot_token) and not self.telegram_bot_token.startswith("your_")

    @property
    def has_gemini(self) -> bool:
        return bool(self.gemini_api_key) and not self.gemini_api_key.startswith("your_")


settings = Settings()
