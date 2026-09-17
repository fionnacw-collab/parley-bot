"""
gemini_extractor.py — Universal AI Router & Ingestion Engine powered by Google Gemini.
Parses any input format (Natural text, Sportsbook screenshots, SBOBET bet slips, Multi-page PDFs)
into clean structured ExtractedMatch domain objects with ZERO match limits.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import re
from PIL import Image
import pymupdf

from config import settings
from models import ExtractedMatch

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """\
You are an expert sports betting and football match parser with OCR capabilities.
Analyze ALL provided text, screenshots, photos, tables, and document pages.
Extract EVERY SINGLE football match / fixture visible without omitting any match.
Whether there are 1, 5, 15, 30, or 50 matches, extract ALL of them completely.

Return ONLY a valid JSON array of objects with:
- "home": Clean standard home team name (e.g. "Arsenal", "Dayrout", "Manchester City", "El Dakhleya")
- "away": Clean standard away team name (e.g. "Chelsea", "El Entag El Harby", "Norwich City", "Tersana")
- "user_pick": Bet pick if explicitly visible (e.g. "Over 2.5", "Arsenal -0.5", "BTTS Yes", etc.), or "" if none.
- "user_odds": Decimal odds if visible (e.g. 1.85, 2.10, -1.15), or 0.0 if none.
- "league": League name if visible (e.g. "Premier League", "La Liga", "Egypt Division 2"), or "" if none.

Return ONLY pure JSON array. Do NOT summarize or truncate.
"""


def _parse_extracted_json(raw: str) -> list[ExtractedMatch]:
    """Parse JSON string into ExtractedMatch objects."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("\n", 1)[0]
        raw = raw.strip()

    try:
        data = json.loads(raw)
    except Exception:
        return []

    matches: list[ExtractedMatch] = []
    seen = set()

    for item in data:
        home = str(item.get("home", "")).strip()
        away = str(item.get("away", "")).strip()
        user_pick = str(item.get("user_pick", "")).strip()
        user_odds = float(item.get("user_odds", 0.0) or 0.0)
        league = str(item.get("league", "")).strip()

        if not home or not away:
            continue

        key = (home.lower(), away.lower())
        if key in seen:
            continue
        seen.add(key)

        matches.append(
            ExtractedMatch(
                home=home,
                away=away,
                user_pick=user_pick,
                user_odds=user_odds,
                league=league,
            )
        )

    return matches


# ---------------------------------------------------------------------------
# 1. Direct Regex Match Parser (0ms execution)
# ---------------------------------------------------------------------------

_MATCH_LINE_RE = re.compile(
    r"^\s*(?:\[?\d+[.)\]]|\*|-|•)?\s*"
    r"(?P<home>[a-zA-Z0-9\s.\'-]+?)"
    r"\s+(?:vs?\.?|v|lawan|ketemu)\s+"
    r"(?P<away>[a-zA-Z0-9\s.\'-]+?)"
    r"(?:\s+[-–—:]\s+(?P<pick>[^@\n\r]+?))?"
    r"(?:\s*[@:]\s*(?P<odds>[-+]?\d+(?:\.\d+)?|\([-+]?\d+(?:\.\d+)?\)))?"
    r"\s*$",
    re.IGNORECASE,
)


def extract_matches_from_text_fast(text: str) -> list[ExtractedMatch]:
    """Fast local regex extraction for match lines (0ms)."""
    lines = text.strip().splitlines()
    matches: list[ExtractedMatch] = []
    seen = set()

    for line in lines:
        line_clean = line.strip()
        if not line_clean or line_clean.startswith("#"):
            continue

        m = _MATCH_LINE_RE.match(line_clean)
        if m:
            home = m.group("home").strip()
            away = m.group("away").strip()
            pick = (m.group("pick") or "").strip()
            raw_odds = m.group("odds") or "0.0"

            odds_val = 0.0
            try:
                odds_val = float(raw_odds.replace("(", "").replace(")", "").strip())
            except Exception:
                pass

            if home and away and len(home) >= 2 and len(away) >= 2:
                key = (home.lower(), away.lower())
                if key not in seen:
                    seen.add(key)
                    matches.append(
                        ExtractedMatch(
                            home=home,
                            away=away,
                            user_pick=pick,
                            user_odds=odds_val,
                        )
                    )

    return matches


async def extract_matches_from_text(text: str) -> list[ExtractedMatch]:
    """
    Extract matches from text.
    First tries fast regex (0ms); if conversational, uses Gemini AI router.
    """
    fast_matches = extract_matches_from_text_fast(text)
    if fast_matches:
        return fast_matches

    # Conversational text query: Route through Gemini
    if settings.has_gemini:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=settings.gemini_api_key)
            prompt = f"{_EXTRACTION_PROMPT}\n\nInput Text:\n{text}"

            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=settings.gemini_model,
                    contents=[prompt],
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=8192,
                        response_mime_type="application/json",
                    ),
                ),
                timeout=4.0,
            )
            raw = response.text or "[]"
            return _parse_extracted_json(raw)
        except Exception as e:
            logger.warning(f"Conversational Gemini text extraction error: {e}")

    return []


# ---------------------------------------------------------------------------
# 2. Image & Screenshot Extraction (Single or Multiple / Albums)
# ---------------------------------------------------------------------------

async def extract_matches_from_images(images: list[bytes]) -> list[ExtractedMatch]:
    """Extract ALL matches across one or multiple images/screenshots without limits."""
    if not images:
        return []

    if not settings.has_gemini:
        raise ValueError("GEMINI_API_KEY belum disetel di .env.")

    # Compress images to optimized lightweight JPEGs
    compressed_parts = []
    for b in images:
        try:
            pil_img = Image.open(io.BytesIO(b)).convert("RGB")
            # Resize if overly large for super fast upload & crystal clear OCR
            if pil_img.width > 1400:
                h = int(pil_img.height * (1400 / pil_img.width))
                pil_img = pil_img.resize((1400, h), Image.Resampling.BILINEAR)
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=82, optimize=True)
            compressed_parts.append(buf.getvalue())
        except Exception:
            compressed_parts.append(b)

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    contents = [_EXTRACTION_PROMPT]
    for c_bytes in compressed_parts:
        contents.append(types.Part.from_bytes(data=c_bytes, mime_type="image/jpeg"))

    try:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=settings.gemini_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=8192,
                    response_mime_type="application/json",
                ),
            ),
            timeout=8.0,
        )
        raw = response.text or "[]"
        return _parse_extracted_json(raw)
    except Exception as e:
        logger.exception("Failed to extract matches from images")
        raise ValueError(f"Gagal membaca gambar via AI Vision: {e}")


async def extract_matches_from_image(image_bytes: bytes) -> list[ExtractedMatch]:
    """Extract matches from a single image."""
    return await extract_matches_from_images([image_bytes])


# ---------------------------------------------------------------------------
# 3. Multi-Page PDF Document Extraction (Up to 50 Pages without limits)
# ---------------------------------------------------------------------------

async def extract_matches_from_pdf(pdf_bytes: bytes, max_pages: int = 50) -> tuple[list[ExtractedMatch], int]:
    """
    Extract matches from a multi-page PDF document without artificial limits.
    Instant text extraction (0ms), with high-capacity vision for image PDFs.
    """
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
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

        # Render at 96 DPI JPEG for vision
        pix = page.get_pixmap(dpi=96)
        try:
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80, optimize=True)
            rendered_jpegs.append(buf.getvalue())
        except Exception:
            rendered_jpegs.append(pix.tobytes("png"))

    doc.close()

    # 1. Check if PDF contains selectable text (0ms instant extraction!)
    text_matches = extract_matches_from_text_fast(all_text)
    if text_matches:
        return text_matches, total_pages

    # 2. Vision extraction for scanned / screenshot PDFs in high-capacity batches
    if rendered_jpegs and settings.has_gemini:
        all_vision_matches: list[ExtractedMatch] = []
        batch_size = 10  # process up to 10 pages per API call

        for i in range(0, len(rendered_jpegs), batch_size):
            batch = rendered_jpegs[i : i + batch_size]
            try:
                matches = await extract_matches_from_images(batch)
                all_vision_matches.extend(matches)
            except Exception as e:
                logger.warning(f"PDF batch vision call error: {e}")

        if all_vision_matches:
            # Deduplicate across pages
            unique_matches: list[ExtractedMatch] = []
            seen = set()
            for m in all_vision_matches:
                key = (m.home.lower(), m.away.lower())
                if key not in seen:
                    seen.add(key)
                    unique_matches.append(m)
            return unique_matches, total_pages

    return text_matches, total_pages
