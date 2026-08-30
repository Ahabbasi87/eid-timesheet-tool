"""
Central configuration for all business rules.
Edit values here to change shift timing, break duration, matching behavior,
or validation thresholds WITHOUT touching any processing logic elsewhere
in the application.
"""
from datetime import time

# ---------------------------------------------------------------------------
# Shift / timesheet rules
# ---------------------------------------------------------------------------
SHIFT_TIME_IN = time(6, 0)      # 6:00 AM
SHIFT_TIME_OUT = time(18, 0)    # 6:00 PM
SHIFT_BREAK_HOURS = 2.0
MAX_WORKED_HOURS = 10.0         # hard cap unless overridden below
ALLOW_EXCEEDING_MAX_HOURS = False

# ---------------------------------------------------------------------------
# Timesheet template layout
# ---------------------------------------------------------------------------
SUPPLIER_NAME_CELL = "H5"       # cell holding supplier/company name in each template
# Column letters for each field in the timesheet's employee data rows.
# Adjust these if a template's layout differs.
TIMESHEET_COLUMNS = {
    "eid_no": "A",
    "employee_name": "B",
    "designation": "C",
    "time_in": "D",
    "break_hours": "E",
    "time_out": "F",
    "total_hours": "G",
}
TIMESHEET_FIRST_DATA_ROW = 7  # first row where employee data should be written

# ---------------------------------------------------------------------------
# Master data expected columns (header names, case-insensitive match)
# ---------------------------------------------------------------------------
MASTER_COLUMNS = {
    "eid_no": ["eid no", "eid no.", "eid number", "emirates id no"],
    "nationality": ["nationality"],
    "employee_name": ["employee name", "name"],
    "designation": ["designation"],
    "doj": ["date of joining", "doj"],
    "supplier": ["supplier name", "company name as per license", "supplier", "company name"],
    "eid_expiry": ["eid expiry date", "eid expiry", "expiry date"],
}

# ---------------------------------------------------------------------------
# EID validation
# ---------------------------------------------------------------------------
# Standard UAE Emirates ID format: 784-YYYY-XXXXXXX-X (15 digits total)
EID_REGEX = r"784-?\d{4}-?\d{7}-?\d{1}"
EID_DIGIT_COUNT = 15

# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------
OCR_MIN_CONFIDENCE = 40  # 0-100 scale; below this -> exception
OCR_ENGINE = "easyocr"  # pip-only, no admin/system install required; swappable later without changing callers

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
NEW_ARRIVALS_SHEET_NAME = "New Arrivals Data Not Found"
PROCESSING_LOG_SHEET_NAME = "Processing Log"
SUMMARY_SHEET_NAME = "Processing Summary"
NEW_ARRIVALS_REMARK = "New Arrivals - Data Not Found in Master Data"
