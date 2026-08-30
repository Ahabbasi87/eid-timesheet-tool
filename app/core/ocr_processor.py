"""
OCR extraction for scanned Emirates ID images and PDFs.

Uses Tesseract OCR (via the pytesseract wrapper) with OpenCV preprocessing
tuned for the busy security-pattern background on Emirates ID cards.
Tesseract is a small, well-established OCR engine - unlike EasyOCR (which
pulls in PyTorch, a multi-hundred-MB machine learning library), Tesseract
has a tiny memory footprint, which matters on a free-tier cloud server
with limited RAM. The system `tesseract-ocr` package is installed via
packages.txt (see repo root) - Streamlit Community Cloud reads that file
automatically during build. The OCR_ENGINE config flag exists so this can
be swapped for a different engine later without touching any calling code
- callers only depend on extract_eids_from_source().

Handles two real-world shapes of input, both via the same code path:
  - one ID card per image/page (the simple case)
  - several ID cards scanned onto a single page/image (common when a
    batch of physical IDs is photocopied or scanned together, e.g. a
    2x4 grid on one sheet) - every EID pattern found on the page is
    returned as its own ExtractedID record, tagged with which page/
    position it came from.
PDF files are rendered to images (one image per page) via PyMuPDF before
the same OCR path runs on each page.
"""
import re
from pathlib import Path

import cv2
import numpy as np

from app.core.config import EID_REGEX
from app.core.eid_utils import clean_eid, is_valid_eid
from app.models.schemas import ExtractedID

# A single ID card's ID-number line is usually much shorter than the
# amount of stray text OCR can produce from a busy security background,
# so anything absurdly long is almost certainly noise, not a real EID
# line, and is skipped before regex matching to cut down false splits.
_MAX_CANDIDATE_LEN = 40


def _preprocess(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img

    # upscale small scans - improves digit recognition significantly
    h, w = gray.shape
    if max(h, w) < 2000:
        scale = 2000 / max(h, w)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # denoise the security-pattern background, then sharpen contrast
    denoised = cv2.fastNlMeansDenoising(gray, h=15)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    contrast = clahe.apply(denoised)

    # adaptive threshold works better than global threshold on ID card glare
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
    """Render every page of a PDF to a BGR numpy image (OpenCV format)."""
    import fitz  # PyMuPDF - pure pip package, no poppler/system install needed

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
    """Runs Tesseract OCR on one image, returns list of (text, confidence 0-100)."""
    import pytesseract  # imported lazily so app startup stays fast

    processed = _preprocess(img)
    data = pytesseract.image_to_data(
        processed, output_type=pytesseract.Output.DICT, config="--psm 6"
    )
    detections = []
    for text, conf in zip(data["text"], data["conf"]):
        text = text.strip()
        # tesseract returns -1 confidence for boxes with no recognized text
        conf = float(conf)
        if text and conf >= 0:
            detections.append((text, conf))
    return detections


def _find_eids_in_detections(detections):
    """
    Scans every OCR-detected text fragment for EID-shaped substrings.
    Returns a list of (cleaned_eid, confidence) - one entry per distinct
    EID pattern found, so a page with several ID cards yields several
    entries instead of just the first match.
    """
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

    # fall back: some scans split "784-1999-" and "3972907-7" across two
    # separate OCR boxes - retry against the full concatenated text of
    # the whole page/image for anything not already found. Tesseract
    # returns word-level boxes in reading order, so simple concatenation
    # (with spaces, since words are already space-separated) works.
    full_text = " ".join(t for t, _ in detections)
    avg_conf = sum(c for _, c in detections) / len(detections) if detections else 0.0
    for match in re.finditer(EID_REGEX, full_text.replace(" ", "")):
        cleaned = clean_eid(match.group(0))
        if is_valid_eid(cleaned) and cleaned not in seen:
            seen.add(cleaned)
            found.append((cleaned, round(avg_conf, 1)))

    return found


def _extract_from_single_image(img: np.ndarray, source_file: str, page_label: str = ""):
    label = f"{source_file}{page_label}"
    try:
        detections = _detections_for_image(img)
    except Exception as e:
        return [ExtractedID(source_file=label, raw_ocr_text=f"[OCR engine error: {e}]")]

    eids = _find_eids_in_detections(detections)
    full_text = " ".join(t for t, _ in detections)

    if not eids:
        return [ExtractedID(source_file=label, raw_ocr_text=full_text)]

    results = []
    for i, (eid, conf) in enumerate(eids, start=1):
        tag = label if len(eids) == 1 else f"{label} [card {i}]"
        results.append(ExtractedID(
            source_file=tag,
            raw_ocr_text=full_text,
            cleaned_eid=eid,
            ocr_confidence=conf,
        ))
    return results


def extract_eids_from_source(path: str, source_file: str):
    """
    Runs OCR against one uploaded file - a single-card image, a
    multi-card image, or a (possibly multi-page, possibly multi-card-
    per-page) PDF - and returns a list of ExtractedID, one per ID card
    found. Does NOT raise on OCR/read failure - failures are represented
    as a single ExtractedID with no cleaned_eid so the caller can log
    them, per the "never silently ignore an error" rule.
    """
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
    """
    Back-compat single-result wrapper for older callers: returns only the
    first EID found (or the failure record). New code should call
    extract_eids_from_source() instead, which handles multi-ID pages.
    """
    results = extract_eids_from_source(image_path, source_file)
    return results[0]

