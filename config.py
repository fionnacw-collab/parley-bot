"""
config.py — Centralized configuration and environment loader.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    rapidapi_key: str = os.getenv("RAPIDAPI_KEY", "")
    odds_api_key: str = os.getenv("ODDS_API_KEY", "")

    # Web & Hosting
    port: int = int(os.getenv("PORT", "8080"))
    host: str = os.getenv("HOST", "0.0.0.0")

    # AI Model
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Analysis Defaults
    default_fractional_kelly: float = float(os.getenv("KELLY_FRACTION", "0.25"))
    min_value_threshold: float = float(os.getenv("MIN_VALUE_THRESHOLD", "0.03"))  # +3% EV minimum

    @property
    def has_telegram(self) -> bool:
        return bool(self.telegram_bot_token) and self.telegram_bot_token != "TOKEN_BOT_KAMU"

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key) and self.openai_api_key != "your_openai_api_key_here"

    @property
    def has_rapidapi(self) -> bool:
        return bool(self.rapidapi_key) and self.rapidapi_key != "API_KEY_KAMU"

    @property
    def has_odds_api(self) -> bool:
        return bool(self.odds_api_key) and self.odds_api_key != "API_KEY_KAMU"


settings = Settings()
