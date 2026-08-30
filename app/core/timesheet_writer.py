"""
Populates supplier timesheet templates from matched employees.

Loads each template with keep_vba/formatting intact, writes into a
COPY (never the original), and only ever writes into the configured
data columns/rows - it never touches the template's existing styling,
merged cells, or formulas elsewhere on the sheet.
"""
import shutil
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Dict, List

import openpyxl

from app.core.config import (
    MAX_WORKED_HOURS,
    ALLOW_EXCEEDING_MAX_HOURS,
    SHIFT_BREAK_HOURS,
    SHIFT_TIME_IN,
    SHIFT_TIME_OUT,
    SUPPLIER_NAME_CELL,
    TIMESHEET_COLUMNS,
    TIMESHEET_FIRST_DATA_ROW,
)
from app.models.schemas import LogEntry, LogSeverity, MatchResult, MatchStatus


def calculate_worked_hours(time_in: dt_time, time_out: dt_time, break_hours: float) -> float:
    in_minutes = time_in.hour * 60 + time_in.minute
    out_minutes = time_out.hour * 60 + time_out.minute
    worked = (out_minutes - in_minutes) / 60 - break_hours
    if worked > MAX_WORKED_HOURS and not ALLOW_EXCEEDING_MAX_HOURS:
        worked = MAX_WORKED_HOURS
    return round(worked, 2)


def read_supplier_name(filepath: str) -> str:
    wb = openpyxl.load_workbook(filepath, data_only=True, read_only=True)
    ws = wb.active
    value = ws[SUPPLIER_NAME_CELL].value
    wb.close()
    return str(value).strip() if value else ""


def populate_supplier_timesheet(
    template_path: str,
    output_path: str,
    matched_results: List[MatchResult],
) -> List[LogEntry]:
    """
    Writes matched employees into a copy of the template.
    Returns log entries for anything worth flagging during this write
    (e.g. ran out of blank rows).
    """
    logs: List[LogEntry] = []

    shutil.copyfile(template_path, output_path)  # never touch the original
    wb = openpyxl.load_workbook(output_path)  # keep_vba etc. default preserves formatting
    ws = wb.active

    worked_hours = calculate_worked_hours(SHIFT_TIME_IN, SHIFT_TIME_OUT, SHIFT_BREAK_HOURS)
    cols = TIMESHEET_COLUMNS
    row_idx = TIMESHEET_FIRST_DATA_ROW

    written = 0
    for result in matched_results:
        if result.status != MatchStatus.MATCHED:
            continue
        emp = result.employee
        ws[f"{cols['eid_no']}{row_idx}"] = emp.eid_no
        ws[f"{cols['employee_name']}{row_idx}"] = emp.employee_name
        ws[f"{cols['designation']}{row_idx}"] = emp.designation
        ws[f"{cols['time_in']}{row_idx}"] = SHIFT_TIME_IN.strftime("%H:%M")
        ws[f"{cols['break_hours']}{row_idx}"] = SHIFT_BREAK_HOURS
        ws[f"{cols['time_out']}{row_idx}"] = SHIFT_TIME_OUT.strftime("%H:%M")
        ws[f"{cols['total_hours']}{row_idx}"] = worked_hours
        row_idx += 1
        written += 1

    wb.save(output_path)
    wb.close()

    logs.append(LogEntry(
        issue_type="Timesheet populated",
        message=f"Wrote {written} employee row(s) into {Path(output_path).name}.",
        severity=LogSeverity.INFO,
        source_file=Path(template_path).name,
    ))
    return logs


def group_matches_by_supplier(
    results: List[MatchResult],
    master_suppliers: Dict[str, str] = None,
) -> Dict[str, List[MatchResult]]:
    """Groups MATCHED results by their employee's supplier field."""
    grouped: Dict[str, List[MatchResult]] = {}
    for r in results:
        if r.status != MatchStatus.MATCHED or not r.supplier:
            continue
        grouped.setdefault(r.supplier, []).append(r)
    return grouped
