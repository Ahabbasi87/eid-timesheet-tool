"""
Utilities for cleaning and validating Emirates ID numbers.
Central place for EID format rules so matching stays consistent
across master data loading, OCR extraction, and duplicate detection.
"""
import re
from app.core.config import EID_DIGIT_COUNT


def clean_eid(raw: str) -> str:
    """
    Strip everything except digits, then re-insert the standard
    784-YYYY-XXXXXXX-X hyphenation if the digit count matches a valid EID.
    Returns '' if the cleaned value doesn't look like a plausible EID.
    """
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)

    # common OCR slip: leading 7 read as nothing, or trailing noise
    if len(digits) > EID_DIGIT_COUNT:
        # try trimming trailing junk digits first
        digits = digits[:EID_DIGIT_COUNT]
    if len(digits) != EID_DIGIT_COUNT:
        return ""
    if not digits.startswith("784"):
        return ""

    return f"{digits[0:3]}-{digits[3:7]}-{digits[7:14]}-{digits[14:15]}"


def is_valid_eid(cleaned: str) -> bool:
    if not cleaned:
        return False
    return bool(re.fullmatch(r"784-\d{4}-\d{7}-\d{1}", cleaned))
