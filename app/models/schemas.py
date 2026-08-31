"""
Core data structures used across the processing pipeline.
Kept as plain dataclasses (not a DB) since the Excel files ARE the
system of record - this app is a stateless processing session.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class MatchStatus(str, Enum):
    MATCHED = "matched"
    NEW_ARRIVAL = "new_arrival"
    DUPLICATE = "duplicate"
    OCR_ERROR = "ocr_error"
    INVALID_FORMAT = "invalid_format"
    SUPPLIER_MISMATCH = "supplier_mismatch"


class LogSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class MasterEmployee:
    eid_no: str
    employee_name: str = ""
    nationality: str = ""
    designation: str = ""
    doj: str = ""
    supplier: str = ""
    eid_expiry: str = ""


@dataclass
class ExtractedID:
    source_file: str
    raw_ocr_text: str = ""
    cleaned_eid: Optional[str] = None
    ocr_confidence: float = 0.0
    # Best-effort fields read directly off the card - only reliably
    # populated for single-card scans (see ocr_processor.py notes).
    name: str = ""
    date_of_issue: str = ""
    date_of_expiry: str = ""


@dataclass
class MatchResult:
    source_file: str
    extracted_eid: Optional[str]
    status: MatchStatus
    employee: Optional[MasterEmployee] = None
    supplier: Optional[str] = None
    notes: str = ""
    # Populated for NEW_ARRIVAL results only - these come from OCR
    # reading the card itself, since there's no master data record.
    extracted_name: str = ""
    extracted_date_of_issue: str = ""
    extracted_date_of_expiry: str = ""


@dataclass
class LogEntry:
    issue_type: str
    message: str
    severity: LogSeverity = LogSeverity.INFO
    eid_no: Optional[str] = None
    source_file: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ProcessingSummary:
    total_eids_uploaded: int = 0
    successfully_matched: int = 0
    new_arrivals: int = 0
    duplicate_eids: int = 0
    processing_errors: int = 0
    total_suppliers: int = 0
    total_employees_processed: int = 0
    timesheets_completed: int = 0
