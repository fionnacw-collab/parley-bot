"""
vision.py — Bet slip & document recognition using Google Gemini (Free) or OpenAI Vision.
Extracts all matches, markets, selections, and odds from images, photo albums, and multi-page PDF documents.
"""

from __future__ import annotations

import base64
import json
import logging
import pymupdf

from config import settings
from models import Leg, MarketCategory
from parser import parse_legs

logger = logging.getLogger(__name__)

_VISION_PROMPT = """\
You are an expert sports betting slip and match document parser.
The input consists of one or more screenshots, photos, or document pages containing sports bet slips, odds lists, or match schedules (e.g., SBOBET, Bet365, 1xBet, CMD368, Maxbet, Sofascore, Flashscore, etc.).

Carefully examine ALL provided images/pages and extract EVERY single match, bet leg, or match event visible across all pages.
For each leg, return a JSON object with:
- "home": Home team name (clean standard club name, e.g. "Arsenal")
- "away": Away team name (clean standard club name, e.g. "Chelsea")
- "pick": The selected bet or match prediction (e.g. "Over 2.5", "Under 3.0", "Home Win", "Away +0.5", "BTTS Yes", etc.)
- "odds": Decimal odds as a float (e.g. 1.85). If shown in Indonesian/Malay/HK format (-115, 0.85), convert to decimal odds. Default to 1.85 if odds are not visible.
- "market": One of ["1X2", "Over/Under", "Both Teams to Score", "Handicap", "Double Chance", "General Market"]

Return ONLY a valid JSON array of objects.
If no bets or matches are visible, return [].
Example output:
[
  {"home": "Arsenal", "away": "Chelsea", "pick": "Over 2.5", "odds": 1.85, "market": "Over/Under"},
  {"home": "Real Madrid", "away": "Barcelona", "pick": "Real Madrid", "odds": 2.10, "market": "1X2"}
]
"""


def _parse_legs_json(raw: str) -> list[Leg]:
    """Parse JSON output into structured Leg domain models."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("\n", 1)[0]
        raw = raw.strip()

    data = json.loads(raw)
    legs: list[Leg] = []
    seen = set()

    for item in data:
        try:
            home = str(item.get("home", "")).strip()
            away = str(item.get("away", "")).strip()
            pick = str(item.get("pick", "")).strip()
            odds = float(item.get("odds", 1.85))

            if not home or not away:
                continue

            # Deduplicate if duplicate match & pick occurs across pages
            key = (home.lower(), away.lower(), pick.lower())
            if key in seen:
                continue
            seen.add(key)

            m_str = str(item.get("market", ""))
            try:
                market = MarketCategory(m_str)
            except Exception:
                market = MarketCategory.OTHER

            legs.append(
                Leg(
                    home=home,
                    away=away,
                    pick=pick or f"{home} Win",
                    odds=odds,
                    market=market,
                    raw=f"{home} vs {away} - {pick} @{odds}",
                )
            )
        except Exception as item_err:
            logger.warning(f"Error parsing leg item: {item_err}")
            continue

    return legs


async def _extract_legs_gemini(images: list[bytes]) -> list[Leg]:
    """Extract legs using Google Gemini Vision."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    contents: list = [_VISION_PROMPT]

    for img_bytes in images:
        contents.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))

    response = await client.aio.models.generate_content(
        model=settings.gemini_model,
        contents=contents,
        config=types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )

    raw = response.text or "[]"
    return _parse_legs_json(raw)


async def _extract_legs_openai(images: list[bytes]) -> list[Leg]:
    """Extract legs using OpenAI Vision."""
    from openai import AsyncOpenAI, RateLimitError

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    user_content: list[dict] = [{"type": "text", "text": _VISION_PROMPT}]

    for img_bytes in images:
        b64_image = base64.b64encode(img_bytes).decode("utf-8")
        user_content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64_image}",
                    "detail": "high",
                },
            }
        )

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=2500,
            temperature=0.1,
        )
        raw = response.choices[0].message.content or "[]"
        return _parse_legs_json(raw)
    except RateLimitError:
        raise ValueError(
            "Saldo OpenAI ($0) habis. Kamu bisa beralih ke Google Gemini (100% Gratis) dengan mengisi GEMINI_API_KEY di .env!"
        )


async def extract_legs_from_images(images: list[bytes]) -> list[Leg]:
    """
    Send images to the active AI Vision provider (Gemini or OpenAI).
    """
    if not images:
        return []

    provider = settings.active_ai_provider

    if provider == "gemini":
        try:
            return await _extract_legs_gemini(images)
        except Exception as e:
            logger.exception("Gemini Vision extraction error")
            raise ValueError(f"Gagal memproses gambar via Gemini: {e}")

    elif provider == "openai":
        try:
            return await _extract_legs_openai(images)
        except Exception as e:
            logger.exception("OpenAI Vision extraction error")
            raise e

    else:
        raise ValueError(
            "Belum ada API Key AI yang aktif. Kamu bisa menggunakan Google Gemini (100% Gratis) dengan memasukkan GEMINI_API_KEY di file .env."
        )


async def extract_legs_from_image(image_bytes: bytes) -> list[Leg]:
    """Extract legs from a single image."""
    return await extract_legs_from_images([image_bytes])


async def extract_legs_from_pdf(pdf_bytes: bytes, max_pages: int = 20) -> tuple[list[Leg], int]:
    """
    Parse a multi-page PDF document, extracting matches via text parsing and/or
    rendering pages to high-res images for AI Vision analysis.
    Returns (legs, total_pages).
    """
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        logger.exception("Failed to open PDF document")
        raise ValueError(f"File PDF tidak valid atau rusak: {e}")

    total_pages = len(doc)
    if total_pages == 0:
        return [], 0

    pages_to_process = min(total_pages, max_pages)
    all_text = ""
    rendered_images: list[bytes] = []

    for page_idx in range(pages_to_process):
        page = doc.load_page(page_idx)
        text = page.get_text()
        if text:
            all_text += text + "\n"

        pix = page.get_pixmap(dpi=150)
        rendered_images.append(pix.tobytes("png"))

    doc.close()

    # 1. Text parsing attempt if PDF contains selectable text
    text_legs = parse_legs(all_text) if all_text.strip() else []

    # 2. Vision attempt if AI provider is active
    vision_legs: list[Leg] = []
    vision_error = None

    if rendered_images and settings.has_ai:
        batch_size = 5
        for i in range(0, len(rendered_images), batch_size):
            batch = rendered_images[i : i + batch_size]
            try:
                legs = await extract_legs_from_images(batch)
                vision_legs.extend(legs)
            except Exception as err:
                vision_error = err
                break

    # Combine results and deduplicate
    combined_legs: list[Leg] = []
    seen = set()

    source_legs = vision_legs if vision_legs else text_legs
    for leg in source_legs:
        key = (leg.home.lower(), leg.away.lower(), leg.pick.lower())
        if key not in seen:
            seen.add(key)
            combined_legs.append(leg)

    if not combined_legs and vision_error:
        raise vision_error

    return combined_legs, total_pages
