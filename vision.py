"""
vision.py — State-of-the-art bet slip recognition using OpenAI Vision (GPT-4o-mini).
Extracts all matches, markets, selections, and odds with zero local OCR dependencies.
"""

from __future__ import annotations

import base64
import json
import logging
from openai import AsyncOpenAI

from config import settings
from models import Leg, MarketCategory

logger = logging.getLogger(__name__)

_VISION_PROMPT = """\
You are an expert sports betting slip parser.
The image contains a bet slip or match screenshot from a sportsbook (e.g., SBOBET, Bet365, 1xBet, CMD368, Maxbet).

Extract EVERY bet/leg visible in the screenshot. For each leg, return a JSON object with:
- "home": Home team name (clean, standard club name)
- "away": Away team name (clean, standard club name)
- "pick": The selected bet (e.g. "Over 2.5", "Under 3.0", "Home Win", "Away +0.5", "BTTS Yes", etc.)
- "odds": Decimal odds as a float (e.g. 1.85). If shown in Indonesian/Malay format (-115, 0.85), convert to decimal.
- "market": One of ["1X2", "Over/Under", "Both Teams to Score", "Handicap", "Double Chance", "General Market"]

Return ONLY a valid JSON array of objects.
If no bets are visible, return [].
Example:
[
  {"home": "Arsenal", "away": "Chelsea", "pick": "Over 2.5", "odds": 1.85, "market": "Over/Under"},
  {"home": "Real Madrid", "away": "Barcelona", "pick": "Real Madrid", "odds": 2.10, "market": "1X2"}
]
"""


async def extract_legs_from_image(image_bytes: bytes) -> list[Leg]:
    """
    Send bet slip screenshot to OpenAI Vision and return structured Leg objects.
    """
    if not settings.has_openai:
        raise ValueError("OPENAI_API_KEY belum dikonfigurasi di file .env")

    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _VISION_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64_image}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
            max_tokens=1000,
            temperature=0.1,
        )

        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw.rsplit("\n", 1)[0]
            raw = raw.strip()

        data = json.loads(raw)
        legs: list[Leg] = []

        for item in data:
            try:
                home = str(item.get("home", "")).strip()
                away = str(item.get("away", "")).strip()
                pick = str(item.get("pick", "")).strip()
                odds = float(item.get("odds", 1.85))

                if not home or not away:
                    continue

                m_str = str(item.get("market", ""))
                try:
                    market = MarketCategory(m_str)
                except Exception:
                    market = MarketCategory.OTHER

                legs.append(
                    Leg(
                        home=home,
                        away=away,
                        pick=pick,
                        odds=odds,
                        market=market,
                        raw=f"{home} vs {away} - {pick} @{odds}",
                    )
                )
            except Exception as item_err:
                logger.warning(f"Error parsing leg item: {item_err}")
                continue

        return legs

    except Exception as e:
        logger.exception("Failed to analyze image with OpenAI Vision")
        raise e
