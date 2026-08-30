# EID & Timesheet Processing Tool

Reads scanned Emirates IDs (JPG/PNG/PDF — one ID per file or several IDs on
one sheet/page), matches each EID number against your master employee
Excel, and auto-fills supplier timesheet templates. Produces a
Processing_Report.xlsx with New Arrivals, Processing Log, and Summary
sheets. See `app/core/config.py` to adjust shift times, break hours, or
column layout.

## Deploying this for free, with a permanent bookmarkable link

This app is built for **Streamlit Community Cloud** — free, nothing
installed on your laptop, and unlike a Google Colab session, the URL
**stays the same every time** so you can bookmark it.

You only need two free accounts, both just websites (no software):
**GitHub** (to hold the code) and **Streamlit Community Cloud** (to run it).

### Step 1 — Create a free GitHub account
Go to https://github.com/signup and sign up (just a browser, nothing to install).

### Step 2 — Create a new repository
1. Click the **+** icon (top right) → **New repository**.
2. Name it e.g. `eid-timesheet-tool`.
3. Set it to **Private** (this handles employee ID data).
4. Click **Create repository**.

### Step 3 — Upload the project files
1. On your new repository's page, click **"uploading an existing file"**
   (or Add file → Upload files).
2. Drag in everything from inside this folder — `app/`, `requirements.txt`,
   `streamlit_app.py` — keeping the folder structure (GitHub's drag-and-drop
   preserves subfolders automatically).
3. Scroll down, click **Commit changes**.

### Step 4 — Deploy on Streamlit Community Cloud
1. Go to https://share.streamlit.io and sign in with your GitHub account
   (one click, no separate password to set up).
2. Click **"Create app"** → choose your `eid-timesheet-tool` repository.
3. Main file path: `streamlit_app.py`
4. Click **Deploy**.
5. Wait a few minutes on first deploy — it's installing Python packages and
   will download the OCR model the first time the tool actually processes
   a batch.

You'll get a permanent link like `https://your-app-name.streamlit.app` —
**bookmark this**. It's the same link every time, forever, whether you
open it today or next month.

### Using it day to day
Open your bookmarked link. If nobody has used it in a while, Streamlit
Community Cloud may show a "This app has gone to sleep" screen — just
click **"Yes, get this app back up"** and wait ~30-60 seconds. No
reinstalling, no rerunning any setup — it's the same app, same link.

## What each screen does
1. Upload your Master Employee Excel (EID No., Name, Designation, Supplier,
   etc.)
2. Upload scanned Emirates ID files (JPG/PNG/PDF) — a file can contain one
   ID or several IDs scanned onto one page; every ID card found is
   processed.
3. Upload one timesheet template per supplier (supplier name must be in
   cell H5 of each template).
4. Click **Process Timesheets**.
5. Download the results zip: one populated timesheet per supplier, plus
   `Processing_Report.xlsx` (New Arrivals / Processing Log / Summary).

## Data handling
- Master data and your original templates are **never modified** — only
  new copies are written.
- Matching is by **EID number only** — all other employee details (name,
  designation, etc.) come from your master sheet, never from what OCR
  reads off the ID card, so OCR misreading a name never causes a wrong
  timesheet entry.
- Uploaded files exist only for the current processing run and are
  deleted immediately after — nothing persists between visits.
- Repository is set to Private on GitHub and the app itself has no
  authentication yet — anyone with the exact Streamlit URL could use it.
  For a tool your whole team can rely on with access control, a proper
  cloud deployment with login (Azure/AWS) is the eventual next step.

## Known limitations
- OCR accuracy on real (non-synthetic) scans should be validated with a
  real batch before relying on it for production timesheets — adjust
  `OCR_MIN_CONFIDENCE` in `app/core/config.py` if too many legitimate
  reads get flagged, or too many bad reads get through.
- The timesheet column layout (`TIMESHEET_COLUMNS`,
  `TIMESHEET_FIRST_DATA_ROW` in config.py) assumes one fixed layout across
  all supplier templates — if your real templates vary in structure, this
  may need to become per-template configuration.
- Streamlit Community Cloud's free tier has modest CPU/memory — OCR on a
  large batch of scans in one go may be slow; if that becomes a problem,
  processing in smaller batches works fine.
