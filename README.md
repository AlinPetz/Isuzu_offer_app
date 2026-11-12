# ISUZU Offer App V2

A local Windows/browser app for ISUZU chassis offers. The approved Phase C
catalogue supports 110 configurations: 105 Generation 4 and five Generation 2
M27. Select an exact chassis and consultant, enter client details, and generate
a Romanian commercial PDF with a matching pricing snapshot.

The configurator validates the current Excel row, shows chassis and transport
prices separately, caps the discount at the base chassis price, and handles
catalogued PTO and manual optionals. The server validates the preview against
the current workbook before reserving an offer number. This release preserves
the existing PDF design and does not add Safety Packs or body equipment to
chassis offers.

## Development Setup

Use Python 3.12. From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Open <http://127.0.0.1:8001/>. The stack uses FastAPI/Uvicorn, Jinja2, browser
JavaScript, openpyxl/pandas, ReportLab, Pillow, and PyInstaller for Windows.

## Local Data

Before running or building, obtain the approved workbook through your internal
data channel and put it at `data/Info_sasie_V2.xlsx`. **The workbook is not
included in Git.** The app reads chassis from `sasie` and consultants from
`intern`; the client form is manual. `ISUZU_WORKBOOK_PATH` can point to another
approved V2 workbook for development. Relative paths resolve from the app root.
Save Excel changes and refresh the form; restart when changing the path.

- `offers/`: generated PDFs and matching JSON snapshots with client, consultant,
  and pricing information. Keep both files together to preserve history and numbering.
- `data/chassis_review_approvals.jsonl`: optional local technical review evidence.
- `cache/pdf_images/`: disposable optimized-image cache.
- `.env`: optional local settings. Copy `.env.example` only when needed. The
  separate, existing supplier-import screen uses `OPENAI_API_KEY` and
  `OPENAI_MODEL` if configured; chassis offers do not require a key. Any body
  workbook or supplier uploads must also stay local.

Do not commit real workbooks, offers, uploads, logs, archives, or credentials.
Back up `data/` and `offers/` privately with the app stopped.

## Tests

With the approved workbook in place:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Install Node.js to run the browser/server calculation parity test. The catalogue
regression tests expect the approved 110-row workbook, not an empty template.

## Windows Build

On Windows x64 with Python 3.12 and the approved workbook at the default path:

```powershell
.\build_windows.bat
```

The script creates a fresh PyInstaller `onedir` build under
`build\portable-stage-...\ISUZU_Offer_App\` without overwriting live data.
Smoke-test the staged executable before promoting it to `dist/`. Copy the
entire folder, including `_internal/` and the external `data/`, to a writable
location. Double-click `ISUZU_Offer_App.exe`. It opens the default browser on
port 8001 when available; close the small ISUZU control window to stop it.
Follow `README_START_HERE.txt` inside the build for history transfer.

The Windows executable, build outputs and private rollback copies are not
stored on GitHub.
