"""
gemini_extractor.py — Universal AI Router & Ingestion Engine powered by Google Gemini.
Parses any input format (Natural text, Sportsbook screenshots, SBOBET bet slips, Multi-page PDFs)
into clean structured ExtractedMatch domain objects.
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
You are an expert football match extractor.
Analyze the input text or image(s) and extract EVERY single football match / fixture mentioned.
Return ONLY a valid JSON array of objects with:
- "home": Home team name (clean, standard name, e.g. "Arsenal")
- "away": Away team name (clean, standard name, e.g. "Chelsea")
- "user_pick": Any bet selection if explicitly visible (e.g. "Over 2.5", "Arsenal -0.5", "BTTS Yes", etc.), or "" if none.
- "user_odds": Any decimal odds if visible (e.g. 1.85), or 0.0 if none.
- "league": League or tournament if visible (e.g. "Premier League", "La Liga"), or "" if none.

Return ONLY a valid JSON array. If no matches found, return [].
Example:
[
  {"home": "Arsenal", "away": "Chelsea", "user_pick": "Over 2.5", "user_odds": 1.85, "league": "Premier League"},
  {"home": "Real Madrid", "away": "Barcelona", "user_pick": "", "user_odds": 0.0, "league": "La Liga"}
]
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
    r"(?P<home>[a-zA-Z0-9\s.]+?)"
    r"\s+(?:vs?\.?|v|-|lawan|ketemu)\s+"
    r"(?P<away>[a-zA-Z0-9\s.]+?)"
    r"(?:\s*[-–—:]\s*(?P<pick>[^@\n\r]+?))?"
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
                        response_mime_type="application/json",
                    ),
                ),
                timeout=3.5,
            )
            raw = response.text or "[]"
            return _parse_extracted_json(raw)
        except Exception as e:
            logger.warning(f"Conversational Gemini text extraction error: {e}")

    return []


# ---------------------------------------------------------------------------
# 2. Image & Screenshot Extraction (Gemini Vision)
# ---------------------------------------------------------------------------

async def extract_matches_from_image(image_bytes: bytes) -> list[ExtractedMatch]:
    """Extract matches from a screenshot or photo using Gemini Vision."""
    if not settings.has_gemini:
        raise ValueError("GEMINI_API_KEY belum disetel di .env.")

    # Compress image to lightweight JPEG (<50KB)
    try:
        pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        if pil_img.width > 1200:
            h = int(pil_img.height * (1200 / pil_img.width))
            pil_img = pil_img.resize((1200, h), Image.Resampling.BILINEAR)
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=80, optimize=True)
        compressed_bytes = buf.getvalue()
    except Exception:
        compressed_bytes = image_bytes

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    contents = [
        types.Part.from_bytes(data=compressed_bytes, mime_type="image/jpeg"),
        _EXTRACTION_PROMPT,
    ]

    try:
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
        return _parse_extracted_json(raw)
    except Exception as e:
        logger.exception("Failed to extract matches from image")
        raise ValueError(f"Gagal membaca gambar: {e}")


# ---------------------------------------------------------------------------
# 3. Multi-Page PDF Document Extraction
# ---------------------------------------------------------------------------

async def extract_matches_from_pdf(pdf_bytes: bytes, max_pages: int = 15) -> tuple[list[ExtractedMatch], int]:
    """
    Extract matches from a multi-page PDF document.
    Instant text extraction (0ms), with lightweight single-call vision for image PDFs.
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

    # 2. Vision extraction for scanned / screenshot PDFs
    if rendered_jpegs and settings.has_gemini:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)
        contents = [_EXTRACTION_PROMPT]
        for b in rendered_jpegs[:8]:  # send up to 8 pages in 1 call
            contents.append(types.Part.from_bytes(data=b, mime_type="image/jpeg"))

        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=settings.gemini_model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        response_mime_type="application/json",
                    ),
                ),
                timeout=6.0,
            )
            raw = response.text or "[]"
            vision_matches = _parse_extracted_json(raw)
            if vision_matches:
                return vision_matches, total_pages
        except Exception as e:
            logger.warning(f"PDF Gemini vision call skipped ({e})")

    return text_matches, total_pages
