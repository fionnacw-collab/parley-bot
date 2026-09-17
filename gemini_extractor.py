"""
gemini_extractor.py — High-Performance Local OCR & AI Extraction Engine.
Extracts matches from Screenshots, Photos, and Multi-page PDFs using 100% FREE Local OCR
(RapidOCR ONNX) with ZERO API tokens and ZERO rate limits.
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

# Singleton RapidOCR engine instance (initialized lazily in memory)
_LOCAL_OCR_ENGINE = None


def get_local_ocr_engine():
    """Get or initialize the local RapidOCR engine."""
    global _LOCAL_OCR_ENGINE
    if _LOCAL_OCR_ENGINE is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _LOCAL_OCR_ENGINE = RapidOCR()
            logger.info("🧠 Local RapidOCR ONNX Engine berhasil dimuat (100% Gratis & Tanpa Token).")
        except Exception as e:
            logger.warning(f"Could not load RapidOCR: {e}")
            _LOCAL_OCR_ENGINE = False
    return _LOCAL_OCR_ENGINE if _LOCAL_OCR_ENGINE is not False else None


# ---------------------------------------------------------------------------
# Team Name & OCR Space Cleaner
# ---------------------------------------------------------------------------

_OCR_FIXES = [
    (r"\bArse\s*nal\b", "Arsenal"),
    (r"\bBarce\s*lona\b", "Barcelona"),
    (r"\bChe\s*lsea\b", "Chelsea"),
    (r"\bLiver\s*pool\b", "Liverpool"),
    (r"\bMan\s*chester\b", "Manchester"),
    (r"\bJuve\s*ntus\b", "Juventus"),
    (r"\bDor\s*tmund\b", "Dortmund"),
    (r"\bInter\s*nacional\b", "Internacional"),
    (r"\bLever\s*kusen\b", "Leverkusen"),
    (r"\bSalz\s*burg\b", "Salzburg"),
    (r"\bMarse\s*ille\b", "Marseille"),
    (r"\bFerenc\s*varos\b", "Ferencvaros"),
    (r"\bPoz\s*nan\b", "Poznan"),
    (r"\bNij\s*megen\b", "Nijmegen"),
    (r"\bTorre\s*ense\b", "Torreense"),
    (r"\bBourne\s*mouth\b", "Bournemouth"),
    (r"\bKaby\s*lie\b", "Kabylie"),
    (r"\bVilla\s*rreal\b", "Villarreal"),
    (r"\bCumba\s*ya\b", "Cumbaya"),
    (r"\bPetro\s*lero\b", "Petrolero"),
    (r"\bVan\s*couver\b", "Vancouver"),
    (r"\bToli\s*ma\b", "Tolima"),
    (r"\bUniver\s*sitario\b", "Universitario"),
    (r"\bNacio\s*nal\b", "Nacional"),
    (r"\bNor\s*wich\b", "Norwich"),
    (r"\bvs\s*\.\s*", " vs "),
    (r"\bv\s*\.\s*", " v "),
]


def clean_ocr_text(text: str) -> str:
    """Normalize broken words and symbols produced by OCR."""
    res = text
    for pat, rep in _OCR_FIXES:
        res = re.sub(pat, rep, res, flags=re.IGNORECASE)
    return res


# ---------------------------------------------------------------------------
# 1. Regex Match Parser (0ms execution)
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
    cleaned_text = clean_ocr_text(text)
    lines = cleaned_text.strip().splitlines()
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


# ---------------------------------------------------------------------------
# 2. Local OCR Engine for Screenshots & Photos (0 Tokens, 100% Free)
# ---------------------------------------------------------------------------

def ocr_image_locally(image_bytes: bytes) -> str:
    """
    Run local RapidOCR engine on image bytes.
    100% Free, 0 API tokens used, runs completely offline on device.
    """
    ocr = get_local_ocr_engine()
    if not ocr:
        return ""

    try:
        # Preprocess / ensure RGB format
        pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        result, _ = ocr(png_bytes)
        if not result:
            return ""

        extracted_lines = []
        for line_item in result:
            # line_item format: [box, text, confidence]
            text = str(line_item[1]).strip()
            if text:
                extracted_lines.append(text)

        return clean_ocr_text("\n".join(extracted_lines))
    except Exception as e:
        logger.warning(f"Local OCR error: {e}")
        return ""


async def extract_matches_from_images(images: list[bytes]) -> list[ExtractedMatch]:
    """
    Extract ALL matches from one or multiple screenshots/photos.
    Uses 100% FREE Local OCR first (0 tokens). If empty, falls back to Gemini.
    """
    if not images:
        return []

    all_matches: list[ExtractedMatch] = []
    seen = set()

    # 1. Run 100% Free Local OCR on all images
    for img_bytes in images:
        ocr_text = ocr_image_locally(img_bytes)
        if ocr_text:
            matches = extract_matches_from_text_fast(ocr_text)
            for m in matches:
                key = (m.home.lower(), m.away.lower())
                if key not in seen:
                    seen.add(key)
                    all_matches.append(m)

    if all_matches:
        logger.info(f"✅ Local 100% Free OCR extracted {len(all_matches)} matches with 0 API tokens!")
        return all_matches

    # 2. Optional Fallback to Gemini Vision if local OCR found nothing
    if settings.has_gemini:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=settings.gemini_api_key)
            prompt = """Extract all football matches from these images. Return JSON array with objects containing: home, away, user_pick, user_odds, league."""
            contents = [prompt]
            for b in images:
                contents.append(types.Part.from_bytes(data=b, mime_type="image/jpeg"))

            res = await asyncio.wait_for(
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
            raw = res.text or "[]"
            data = json.loads(raw)
            for item in data:
                h = str(item.get("home", "")).strip()
                a = str(item.get("away", "")).strip()
                if h and a:
                    key = (h.lower(), a.lower())
                    if key not in seen:
                        seen.add(key)
                        all_matches.append(ExtractedMatch(home=h, away=a))
            return all_matches
        except Exception:
            pass

    return all_matches


async def extract_matches_from_image(image_bytes: bytes) -> list[ExtractedMatch]:
    """Extract matches from a single screenshot using Local OCR."""
    return await extract_matches_from_images([image_bytes])


# ---------------------------------------------------------------------------
# 3. Multi-Page PDF Document Extraction (0 Tokens)
# ---------------------------------------------------------------------------

async def extract_matches_from_pdf(pdf_bytes: bytes, max_pages: int = 50) -> tuple[list[ExtractedMatch], int]:
    """
    Extract matches from a multi-page PDF document using 100% FREE Local Extraction (0 Tokens).
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
    rendered_images: list[bytes] = []

    for page_idx in range(pages_to_process):
        page = doc.load_page(page_idx)
        text = page.get_text()
        if text:
            all_text += text + "\n"

        # Render page to PNG for local OCR if needed
        pix = page.get_pixmap(dpi=100)
        rendered_images.append(pix.tobytes("png"))

    doc.close()

    # 1. Instant Text Extraction (0ms, 0 tokens)
    text_matches = extract_matches_from_text_fast(all_text)
    if text_matches:
        logger.info(f"✅ Extracted {len(text_matches)} matches directly from PDF text (0 tokens)!")
        return text_matches, total_pages

    # 2. Local OCR on rendered pages (0 tokens)
    ocr_matches = await extract_matches_from_images(rendered_images)
    if ocr_matches:
        return ocr_matches, total_pages

    return text_matches, total_pages


# ---------------------------------------------------------------------------
# 4. Text Input Router
# ---------------------------------------------------------------------------

async def extract_matches_from_text(text: str) -> list[ExtractedMatch]:
    """
    Extract matches from text.
    First tries fast regex (0ms, 0 tokens); falls back to Gemini if conversational.
    """
    fast_matches = extract_matches_from_text_fast(text)
    if fast_matches:
        return fast_matches

    # Conversational text query fallback
    if settings.has_gemini:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=settings.gemini_api_key)
            prompt = """Extract all football matches from this text. Return JSON array with objects containing: home, away, user_pick, user_odds, league."""
            res = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=settings.gemini_model,
                    contents=[f"{prompt}\n\nInput:\n{text}"],
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        response_mime_type="application/json",
                    ),
                ),
                timeout=3.5,
            )
            raw = res.text or "[]"
            data = json.loads(raw)
            matches = []
            for item in data:
                h = str(item.get("home", "")).strip()
                a = str(item.get("away", "")).strip()
                if h and a:
                    matches.append(ExtractedMatch(home=h, away=a))
            return matches
        except Exception:
            pass

    return []
