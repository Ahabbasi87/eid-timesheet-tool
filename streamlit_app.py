"""
Streamlit front end for the Labor Timesheet Automation Tool.

This is a thin UI layer only - all business logic (OCR, matching,
timesheet writing, reporting) lives in app/core/* and is unchanged from
the FastAPI version. Deploy this file on Streamlit Community Cloud for a
free, permanent, bookmarkable URL (no daily relaunch, unlike a Colab
session) - see DEPLOY.md for step-by-step instructions.
"""
import shutil
import tempfile
import zipfile
from pathlib import Path

import streamlit as st

from app.core.pipeline import run_pipeline

st.set_page_config(page_title="EID & Timesheet Tool", page_icon="🕒", layout="wide")

st.title("🕒 EID & Timesheet Processing Tool")
st.caption(
    "Upload your master employee sheet, scanned Emirates IDs, and supplier "
    "timesheet templates, then click Process. Nothing is installed on your "
    "computer - this all runs on the server."
)

col1, col2, col3 = st.columns(3)
with col1:
    master_file = st.file_uploader(
        "1. Master Employee Sheet (.xlsx)", type=["xlsx"], accept_multiple_files=False
    )
with col2:
    id_files = st.file_uploader(
        "2. Scanned Emirates IDs (JPG/PNG/PDF - one or many IDs per file, one or many files)",
        type=["jpg", "jpeg", "png", "pdf"],
        accept_multiple_files=True,
    )
with col3:
    template_files = st.file_uploader(
        "3. Supplier Timesheet Templates (.xlsx, supplier name in cell H5)",
        type=["xlsx"],
        accept_multiple_files=True,
    )

process_clicked = st.button("▶️ Process Timesheets", type="primary", disabled=not (
    master_file and id_files and template_files
))

if not (master_file and id_files and template_files):
    st.info("Upload all three: master sheet, at least one ID scan, and at least one supplier template.")

if process_clicked:
    with st.spinner(
        "Processing... first run on a fresh server also downloads the OCR "
        "model (a few hundred MB), so this can take a few minutes the "
        "very first time. Later runs are much faster."
    ):
        session_dir = Path(tempfile.mkdtemp(prefix="eid_session_"))
        try:
            scans_dir = session_dir / "scans"
            templates_dir = session_dir / "templates"
            output_dir = session_dir / "output"
            for d in (scans_dir, templates_dir, output_dir):
                d.mkdir(parents=True, exist_ok=True)

            master_path = session_dir / master_file.name
            master_path.write_bytes(master_file.getvalue())

            scan_paths = []
            for f in id_files:
                p = scans_dir / f.name
                p.write_bytes(f.getvalue())
                scan_paths.append(str(p))

            template_paths = []
            for f in template_files:
                p = templates_dir / f.name
                p.write_bytes(f.getvalue())
                template_paths.append(str(p))

            result = run_pipeline(
                master_data_path=str(master_path),
                scanned_id_paths=scan_paths,
                supplier_template_paths=template_paths,
                output_dir=str(output_dir),
            )

            summary = result["summary"]
            st.success("Done.")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("EID cards found", summary.total_eids_uploaded)
            m2.metric("Matched", summary.successfully_matched)
            m3.metric("New arrivals", summary.new_arrivals)
            m4.metric("Errors", summary.processing_errors)
            m5, m6, m7 = st.columns(3)
            m5.metric("Duplicates", summary.duplicate_eids)
            m6.metric("Suppliers processed", summary.total_suppliers)
            m7.metric("Timesheets completed", summary.timesheets_completed)

            # zip every output file for a single download
            zip_path = output_dir / "Results.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in result["output_files"]:
                    zf.write(f, arcname=Path(f).name)

            st.download_button(
                "⬇️ Download all results (timesheets + Processing_Report.xlsx)",
                data=zip_path.read_bytes(),
                file_name="Timesheet_Results.zip",
                mime="application/zip",
                type="primary",
            )

            with st.expander("Individual files"):
                for f in result["output_files"]:
                    fp = Path(f)
                    st.download_button(
                        f"Download {fp.name}",
                        data=fp.read_bytes(),
                        file_name=fp.name,
                        key=f"dl_{fp.name}",
                    )

            errors = [l for l in result["logs"] if l.severity.value == "error"]
            warnings = [l for l in result["logs"] if l.severity.value == "warning"]
            if errors or warnings:
                with st.expander(f"⚠️ {len(errors)} error(s), {len(warnings)} warning(s) - see Processing_Report.xlsx for full detail"):
                    for l in errors + warnings:
                        st.write(f"**[{l.severity.value.upper()}] {l.issue_type}** — {l.message}")
        finally:
            shutil.rmtree(session_dir, ignore_errors=True)

st.divider()
with st.expander("ℹ️ Notes"):
    st.markdown(
        "- Each scan file can contain **one or several ID cards** (e.g. a sheet "
        "with multiple IDs scanned together, or a multi-page PDF) - every ID "
        "card found is processed separately.\n"
        "- Matching is by **EID number only**; all other employee details come "
        "from your master sheet, never from what OCR reads off the card.\n"
        "- Master data and your original templates are **never modified** - "
        "only new copies are written.\n"
        "- Uploaded files exist only for this processing run and are deleted "
        "immediately after - nothing is stored between visits."
    )
