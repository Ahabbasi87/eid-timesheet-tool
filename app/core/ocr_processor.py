"""
OCR extraction for scanned Emirates ID images and PDFs.

Uses Tesseract OCR (via the pytesseract wrapper) with OpenCV preprocessing
tuned for the busy security-pattern background on Emirates ID cards.

Handles two real-world shapes of input, both via the same code path:
  - one ID card per image/page (the simple case)
  - several ID cards scanned onto a single page/image
PDF files are rendered to images (one image per page) via PyMuPDF before
the same OCR path runs on each page.

In addition to the EID number (which follows a rigid 15-digit pattern
and OCRs very reliably), this module also makes a best-effort attempt
at reading the cardholder's Name, Date of Issue, and Date of Expiry
straight off the card - used to fill in the "New Arrivals" report for
EIDs that don't match anything in master data. Unlike the EID number,
these have no fixed shape, so treat them as a head start to be
sanity-checked, not guaranteed-accurate data. Note also: for a page
with SEVERAL ID cards scanned together, this best-effort read only
recognises one name/date set for the whole page (it can't yet tell
which name goes with which of several EIDs on that page) - those
cases are still logged so nothing is silently wrong, but the name/
date columns for multi-card pages should be filled in manually.
"""
import re
from pathlib import Path

import cv2
import numpy as np

from app.core.config import EID_REGEX
from app.core.eid_utils import clean_eid, is_valid_eid
from app.models.schemas import ExtractedID

_MAX_CANDIDATE_LEN = 40

# Matches D/M/Y style dates in whatever separator the card/OCR gives us,
# 2- or 4-digit years.
_DATE_PATTERN = re.compile(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})")

_ISSUE_LABELS = ("issuing", "issue")
_EXPIRY_LABELS = ("expiry", "exp")
_NAME_LABELS = ("name",)
_NAME_STOP_WORDS = {"nationality", "date", "sex", "signature", "occupation", "employer"}


def _preprocess(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    h, w = gray.shape
    if max(h, w) < 2000:
        scale = 2000 / max(h, w)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    denoised = cv2.fastNlMeansDenoising(gray, h=15)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    contrast = clahe.apply(denoised)
    thresh = cv2.adaptiveThreshold(
        contrast, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11
    )
    return thresh


def _load_image(path: str) -> np.ndarray:
    img = cv2.imread(path)
    if img is None:
        raise ValueError(f"Could not read image file: {path}")
    return img


def _pdf_to_images(path: str, dpi: int = 300):
    import fitz  # PyMuPDF

    doc = fitz.open(path)
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    images = []
    for page in doc:
        pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        images.append(bgr)
    doc.close()
    return images


def _detections_for_image(img: np.ndarray):
    import pytesseract

    processed = _preprocess(img)
    data = pytesseract.image_to_data(
        processed, output_type=pytesseract.Output.DICT, config="--psm 6"
    )
    detections = []
    for text, conf in zip(data["text"], data["conf"]):
        text = text.strip()
        conf = float(conf)
        if text and conf >= 0:
            detections.append((text, conf))
    return detections


def _find_eids_in_detections(detections):
    found = []
    seen = set()
    for text, conf in detections:
        compact = text.replace(" ", "")
        if len(compact) > _MAX_CANDIDATE_LEN:
            continue
        for match in re.finditer(EID_REGEX, compact):
            cleaned = clean_eid(match.group(0))
            if is_valid_eid(cleaned) and cleaned not in seen:
                seen.add(cleaned)
                found.append((cleaned, round(conf, 1)))

    full_text = " ".join(t for t, _ in detections)
    avg_conf = sum(c for _, c in detections) / len(detections) if detections else 0.0
    for match in re.finditer(EID_REGEX, full_text.replace(" ", "")):
        cleaned = clean_eid(match.group(0))
        if is_valid_eid(cleaned) and cleaned not in seen:
            seen.add(cleaned)
            found.append((cleaned, round(avg_conf, 1)))

    return found


def _normalize_date(raw_match) -> str:
    d, mo, y = raw_match.groups()
    if len(y) == 2:
        y = "20" + y
    try:
        return f"{int(d):02d}/{int(mo):02d}/{y}"
    except ValueError:
        return ""


def _find_date_near(tokens, start_idx, window=6) -> str:
    """Look forward from start_idx for the first date-shaped token."""
    for j in range(start_idx, min(start_idx + window, len(tokens))):
        m = _DATE_PATTERN.search(tokens[j])
        if m:
            date_str = _normalize_date(m)
            if date_str:
                return date_str
    return ""


def _extract_card_details(detections) -> dict:
    """
    Best-effort read of Name, Date of Issue, and Date of Expiry from the
    OCR'd text of one card image. Looks for the card's own English
    labels ("Name", "Issuing Date", "Expiry Date") and reads the value
    that follows. Returns "" for anything it isn't confident finding -
    callers should treat blanks as "needs manual entry", not an error.
    """
    tokens = [t for t, _ in detections]
    lower_tokens = [t.lower().strip(":") for t in tokens]
    details = {"name": "", "date_of_issue": "", "date_of_expiry": ""}

    for i, tok in enumerate(lower_tokens):
        if not details["date_of_issue"] and any(tok.startswith(l) for l in _ISSUE_LABELS):
            details["date_of_issue"] = _find_date_near(tokens, i + 1)
        if not details["date_of_expiry"] and any(tok.startswith(l) for l in _EXPIRY_LABELS):
            details["date_of_expiry"] = _find_date_near(tokens, i + 1)
        if not details["name"] and tok in _NAME_LABELS:
            name_parts = []
            for j in range(i + 1, min(i + 6, len(tokens))):
                nxt_lower = lower_tokens[j]
                if _DATE_PATTERN.search(tokens[j]) or nxt_lower in _NAME_STOP_WORDS:
                    break
                if re.fullmatch(r"[A-Za-z.'\-]+", tokens[j]):
                    name_parts.append(tokens[j])
                else:
                    break
            if name_parts:
                details["name"] = " ".join(name_parts)

    return details


def _extract_from_single_image(img: np.ndarray, source_file: str, page_label: str = ""):
    label = f"{source_file}{page_label}"
    try:
        detections = _detections_for_image(img)
    except Exception as e:
        return [ExtractedID(source_file=label, raw_ocr_text=f"[OCR engine error: {e}]")]

    eids = _find_eids_in_detections(detections)
    full_text = " ".join(t for t, _ in detections)
    card_details = _extract_card_details(detections)

    if not eids:
        return [ExtractedID(source_file=label, raw_ocr_text=full_text, **card_details)]

    results = []
    for i, (eid, conf) in enumerate(eids, start=1):
        tag = label if len(eids) == 1 else f"{label} [card {i}]"
        results.append(ExtractedID(
            source_file=tag,
            raw_ocr_text=full_text,
            cleaned_eid=eid,
            ocr_confidence=conf,
            name=card_details["name"],
            date_of_issue=card_details["date_of_issue"],
            date_of_expiry=card_details["date_of_expiry"],
        ))
    return results


def extract_eids_from_source(path: str, source_file: str):
    suffix = Path(path).suffix.lower()
    try:
        if suffix == ".pdf":
            pages = _pdf_to_images(path)
            if not pages:
                return [ExtractedID(source_file=source_file, raw_ocr_text="[empty PDF]")]
            all_results = []
            for i, page_img in enumerate(pages, start=1):
                page_label = f" (page {i})" if len(pages) > 1 else ""
                all_results.extend(_extract_from_single_image(page_img, source_file, page_label))
            return all_results
        else:
            img = _load_image(path)
            return _extract_from_single_image(img, source_file)
    except Exception as e:
        return [ExtractedID(source_file=source_file, raw_ocr_text=f"[read error: {e}]")]


def extract_eid_from_image(image_path: str, source_file: str) -> ExtractedID:
    results = extract_eids_from_source(image_path, source_file)
    return results[0]
