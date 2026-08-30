"""
Loads the master employee data workbook into an EID-indexed lookup.
Never writes to this file - read-only by design (business rule: never
overwrite master data).
"""
from typing import Dict, Optional
import openpyxl

from app.core.config import MASTER_COLUMNS
from app.core.eid_utils import clean_eid
from app.models.schemas import MasterEmployee


def _match_header(header_row, aliases_map) -> Dict[str, int]:
    """Map each logical field name -> column index, matching header text
    case-insensitively against configured alias lists."""
    col_map = {}
    normalized = {
        idx: str(cell.value).strip().lower()
        for idx, cell in enumerate(header_row)
        if cell.value is not None
    }
    for field_name, aliases in aliases_map.items():
        for idx, text in normalized.items():
            if text in aliases:
                col_map[field_name] = idx
                break
    return col_map


def load_master_data(filepath: str) -> Dict[str, MasterEmployee]:
    """
    Returns a dict keyed by cleaned EID number -> MasterEmployee.
    Raises ValueError if required columns (eid_no) cannot be found.
    """
    wb = openpyxl.load_workbook(filepath, data_only=True, read_only=True)
    ws = wb.active

    rows = ws.iter_rows()
    header_row = next(rows)
    col_map = _match_header(header_row, MASTER_COLUMNS)

    if "eid_no" not in col_map:
        raise ValueError(
            "Could not find an 'EID No.' column in the master data sheet. "
            "Expected a header matching one of: "
            f"{MASTER_COLUMNS['eid_no']}"
        )

    employees: Dict[str, MasterEmployee] = {}
    for row in rows:
        raw_eid = row[col_map["eid_no"]].value if col_map.get("eid_no") is not None else None
        if raw_eid is None or str(raw_eid).strip() == "":
            continue
        cleaned = clean_eid(str(raw_eid))
        if not cleaned:
            continue

        def get(field_name):
            idx = col_map.get(field_name)
            if idx is None:
                return ""
            val = row[idx].value
            return str(val).strip() if val is not None else ""

        employees[cleaned] = MasterEmployee(
            eid_no=cleaned,
            employee_name=get("employee_name"),
            nationality=get("nationality"),
            designation=get("designation"),
            doj=get("doj"),
            supplier=get("supplier"),
            eid_expiry=get("eid_expiry"),
        )

    wb.close()
    return employees


def find_employee(master: Dict[str, MasterEmployee], eid: str) -> Optional[MasterEmployee]:
    return master.get(clean_eid(eid))
