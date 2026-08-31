"""
Matches extracted EIDs against master data, detects duplicates, and
produces MatchResult + LogEntry records. Pure logic, no I/O - easy to
unit test and to adjust matching rules independently of OCR/Excel code.
"""
from typing import Dict, List, Tuple

from app.core.config import OCR_MIN_CONFIDENCE
from app.core.eid_utils import is_valid_eid
from app.models.schemas import (
    ExtractedID,
    LogEntry,
    LogSeverity,
    MasterEmployee,
    MatchResult,
    MatchStatus,
)


def match_extracted_ids(
    extracted_ids: List[ExtractedID],
    master: Dict[str, MasterEmployee],
) -> Tuple[List[MatchResult], List[LogEntry]]:
    results: List[MatchResult] = []
    logs: List[LogEntry] = []
    seen_eids: Dict[str, str] = {}  # eid -> first source_file that produced it

    for extracted in extracted_ids:
        eid = extracted.cleaned_eid

        # 1. OCR could not produce a usable EID at all
        if not eid:
            results.append(MatchResult(
                source_file=extracted.source_file,
                extracted_eid=None,
                status=MatchStatus.OCR_ERROR,
                notes=f"OCR could not extract a valid EID (raw text: '{extracted.raw_ocr_text[:80]}')",
            ))
            logs.append(LogEntry(
                issue_type="EID could not be read",
                message="OCR failed to produce a valid 15-digit EID from this image.",
                severity=LogSeverity.ERROR,
                source_file=extracted.source_file,
            ))
            continue

        # 2. Low OCR confidence -> flag even if a pattern was matched
        if extracted.ocr_confidence < OCR_MIN_CONFIDENCE:
            results.append(MatchResult(
                source_file=extracted.source_file,
                extracted_eid=eid,
                status=MatchStatus.OCR_ERROR,
                notes=f"OCR confidence {extracted.ocr_confidence}% below threshold ({OCR_MIN_CONFIDENCE}%)",
            ))
            logs.append(LogEntry(
                issue_type="Poor-quality/scanned image",
                message=f"OCR confidence too low ({extracted.ocr_confidence}%) to trust extracted EID {eid}.",
                severity=LogSeverity.WARNING,
                eid_no=eid,
                source_file=extracted.source_file,
            ))
            continue

        # 3. Invalid format safety net (shouldn't normally trigger - clean_eid already validates)
        if not is_valid_eid(eid):
            results.append(MatchResult(
                source_file=extracted.source_file,
                extracted_eid=eid,
                status=MatchStatus.INVALID_FORMAT,
                notes="Extracted value does not match the EID format.",
            ))
            logs.append(LogEntry(
                issue_type="Invalid EID format",
                message=f"'{eid}' does not match the expected 784-YYYY-XXXXXXX-X format.",
                severity=LogSeverity.ERROR,
                eid_no=eid,
                source_file=extracted.source_file,
            ))
            continue

        # 4. Duplicate detection
        if eid in seen_eids:
            results.append(MatchResult(
                source_file=extracted.source_file,
                extracted_eid=eid,
                status=MatchStatus.DUPLICATE,
                notes=f"Duplicate of EID already processed from '{seen_eids[eid]}'.",
            ))
            logs.append(LogEntry(
                issue_type="Duplicate EID",
                message=f"EID {eid} was already processed from '{seen_eids[eid]}'.",
                severity=LogSeverity.WARNING,
                eid_no=eid,
                source_file=extracted.source_file,
            ))
            continue
        seen_eids[eid] = extracted.source_file

        # 5. Master data lookup
          employee = master.get(eid)
            if employee is None:
            results.append(MatchResult(
                source_file=extracted.source_file,
                extracted_eid=eid,
                status=MatchStatus.NEW_ARRIVAL,
                notes="EID not found in master data.",
                extracted_name=extracted.name,
                extracted_date_of_issue=extracted.date_of_issue,
                extracted_date_of_expiry=extracted.date_of_expiry,
            ))
            logs.append(LogEntry(
                issue_type="EID not found in Master Data",
                message=f"EID {eid} was read successfully but has no master data record.",
                severity=LogSeverity.INFO,
                eid_no=eid,
                source_file=extracted.source_file,
            ))
            continue

        # 6. Success
        results.append(MatchResult(
            source_file=extracted.source_file,
            extracted_eid=eid,
            status=MatchStatus.MATCHED,
            employee=employee,
            supplier=employee.supplier,
        ))

    return results, logs
