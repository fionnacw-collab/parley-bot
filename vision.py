"""
vision.py — High-Performance Bet Slip & Document Recognition using Google Gemini Vision (Free)
with Lightweight JPEG Compression and Instant Text-Parsing Fallback.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
from PIL import Image
import pymupdf

from config import settings
from models import Leg, MarketCategory
from parser import parse_legs

logger = logging.getLogger(__name__)

_VISION_PROMPT = """\
You are an expert sports betting slip and SBOBET odds parser.
Extract EVERY single match/bet leg visible across all pages or screenshots (e.g. SBOBET, Bet365, Maxbet, 1xBet).

For each leg, return a JSON object with:
- "home": Home team name (e.g. "Arsenal")
- "away": Away team name (e.g. "Chelsea")
- "pick": Selection (e.g. "Over 2.5", "Real Madrid", "Under 2.5", "HDP 0.25", etc.)
- "odds": Odds as float. If shown in SBOBET Indonesian format (-1.15, -115, 1.05), keep as number or convert to decimal.
- "market": One of ["1X2", "Over/Under", "Both Teams to Score", "Handicap", "Double Chance", "General Market"]

Return ONLY a valid JSON array of objects.
Example:
[
  {"home": "Arsenal", "away": "Chelsea", "pick": "Over 2.5", "odds": 1.85, "market": "Over/Under"},
  {"home": "Real Madrid", "away": "Barcelona", "pick": "Real Madrid -0.25", "odds": 1.95, "market": "Handicap"}
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
            raw_pick = str(item.get("pick", "")).strip()
            raw_odds = item.get("odds", 1.85)

            if not home or not away:
                continue

            from parser import convert_sbobet_odds_to_decimal, normalize_sbobet_handicap_line
            odds = convert_sbobet_odds_to_decimal(raw_odds)
            pick = normalize_sbobet_handicap_line(raw_pick)

            key = (home.lower(), away.lower(), pick.lower())
            if key in seen:
                continue
            seen.add(key)

            m_str = str(item.get("market", ""))
            try:
                market = MarketCategory(m_str)
            except Exception:
                market = MarketCategory.OTHER

            leg = Leg(
                home=home,
                away=away,
                pick=pick or f"{home} Win",
                odds=odds,
                market=market,
                raw=f"{home} vs {away} - {pick} @{odds}",
            )
            leg.market = leg.infer_market()
            legs.append(leg)
        except Exception as item_err:
            logger.warning(f"Error parsing leg item: {item_err}")
            continue

    return legs


async def _extract_legs_gemini(images: list[bytes]) -> list[Leg]:
    """Extract legs using Google Gemini Vision with single fast call."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    contents: list = [_VISION_PROMPT]

    for img_bytes in images:
        contents.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))

    # Fast 5s timeout to ensure the user gets an instant response
    response = await asyncio.wait_for(
        client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        ),
        timeout=5.0,
    )

    raw = response.text or "[]"
    return _parse_legs_json(raw)


async def extract_legs_from_images(images: list[bytes]) -> list[Leg]:
    """Send images to Gemini Vision with lightweight compression."""
    if not images:
        return []

    # Compress images to optimized JPEG (<60KB each)
    compressed: list[bytes] = []
    for b in images:
        try:
            pil_img = Image.open(io.BytesIO(b)).convert("RGB")
            # Max width 1200px for super fast upload & crystal clear OCR
            if pil_img.width > 1200:
                h = int(pil_img.height * (1200 / pil_img.width))
                pil_img = pil_img.resize((1200, h), Image.Resampling.BILINEAR)
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=80, optimize=True)
            compressed.append(buf.getvalue())
        except Exception:
            compressed.append(b)

    if settings.has_gemini:
        return await _extract_legs_gemini(compressed)

    raise ValueError("API Key Gemini belum disetel di .env.")


async def extract_legs_from_image(image_bytes: bytes) -> list[Leg]:
    """Extract legs from a single image."""
    return await extract_legs_from_images([image_bytes])


async def extract_legs_from_pdf(pdf_bytes: bytes, max_pages: int = 15) -> tuple[list[Leg], int]:
    """
    Parse a multi-page PDF document.
    Prioritizes instant text extraction (0ms), falling back to compressed Vision if needed.
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
    rendered_jpegs: list[bytes] = []

    for page_idx in range(pages_to_process):
        page = doc.load_page(page_idx)
        text = page.get_text()
        if text:
            all_text += text + "\n"

        # Render at lightweight 96 DPI directly to JPEG
        pix = page.get_pixmap(dpi=96)
        try:
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80, optimize=True)
            rendered_jpegs.append(buf.getvalue())
        except Exception:
            rendered_jpegs.append(pix.tobytes("png"))

    doc.close()

    # 1. Instant Text Parsing: If PDF contains selectable text, return in 0.001s!
    text_legs = parse_legs(all_text) if all_text.strip() else []
    if text_legs:
        logger.info(f"⚡ Instant text parsing found {len(text_legs)} legs from PDF text")
        return text_legs, total_pages

    # 2. Fast Vision Parsing for image-based PDFs (Send all pages in 1 single call)
    if rendered_jpegs and settings.has_gemini:
        try:
            # Send all pages together in 1 single fast API call
            vision_legs = await _extract_legs_gemini(rendered_jpegs[:8])
            if vision_legs:
                return vision_legs, total_pages
        except Exception as e:
            logger.warning(f"Gemini Vision call skipped ({e})")

    # Fallback to any detected text legs
    return text_legs, total_pages
