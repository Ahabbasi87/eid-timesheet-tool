"""
Top-level orchestration: ties together master data loading, OCR,
matching, timesheet population, and report generation for one
processing run (one "batch" = one set of uploads).
"""
from pathlib import Path
from typing import List

from app.core.master_data import load_master_data
from app.core.matcher import match_extracted_ids
from app.core.ocr_processor import extract_eids_from_source
from app.core.report_writer import build_report_workbook, build_summary
from app.core.timesheet_writer import (
    group_matches_by_supplier,
    populate_supplier_timesheet,
    read_supplier_name,
)
from app.models.schemas import LogEntry, LogSeverity


def run_pipeline(
    master_data_path: str,
    scanned_id_paths: List[str],
    supplier_template_paths: List[str],
    output_dir: str,
):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_logs: List[LogEntry] = []

    # 1. Load master data (read-only)
    master = load_master_data(master_data_path)

    # 2. OCR every scanned ID file. Each file may contain more than one ID
    # card (e.g. several IDs scanned onto one sheet, or a multi-page PDF),
    # so each file can contribute more than one ExtractedID - flatten the
    # per-file lists into one combined list for matching.
    extracted = []
    for path in scanned_id_paths:
        extracted.extend(extract_eids_from_source(path, Path(path).name))

    # 3. Match against master data (also handles dedupe)
    results, match_logs = match_extracted_ids(extracted, master)
    all_logs.extend(match_logs)

    # 4. Read each template's supplier (H5) and validate against master suppliers
    template_suppliers = {}
    for tpath in supplier_template_paths:
        supplier = read_supplier_name(tpath)
        if not supplier:
            all_logs.append(LogEntry(
                issue_type="Missing supplier name in H5",
                message=f"Template '{Path(tpath).name}' has no supplier name in cell H5.",
                severity=LogSeverity.ERROR,
                source_file=Path(tpath).name,
            ))
            continue
        template_suppliers[supplier] = tpath

    # 5. Group matched employees by supplier
    grouped = group_matches_by_supplier(results)

    # 6. Populate each supplier's timesheet
    output_files = []
    timesheets_completed = 0
    for supplier, template_path in template_suppliers.items():
        supplier_matches = grouped.get(supplier, [])
        out_path = output_dir / f"Timesheet_{supplier.replace(' ', '_')}.xlsx"
        write_logs = populate_supplier_timesheet(template_path, str(out_path), supplier_matches)
        all_logs.extend(write_logs)
        output_files.append(str(out_path))
        timesheets_completed += 1

    # 7. Flag matched employees whose supplier had no uploaded template at all
    for supplier, matches in grouped.items():
        if supplier not in template_suppliers:
            for m in matches:
                all_logs.append(LogEntry(
                    issue_type="Supplier mismatch",
                    message=(
                        f"Employee {m.employee.employee_name} ({m.extracted_eid}) belongs to "
                        f"supplier '{supplier}', but no timesheet template was uploaded for that supplier."
                    ),
                    severity=LogSeverity.WARNING,
                    eid_no=m.extracted_eid,
                    source_file=m.source_file,
                ))

    # 8. Build summary + report workbook
    summary = build_summary(
        results, all_logs,
        total_uploaded=len(extracted),
        total_suppliers=len(template_suppliers),
        timesheets_completed=timesheets_completed,
    )
    report_path = output_dir / "Processing_Report.xlsx"
    build_report_workbook(results, all_logs, summary, str(report_path))
    output_files.append(str(report_path))

    return {
        "summary": summary,
        "results": results,
        "logs": all_logs,
        "output_files": output_files,
    }
