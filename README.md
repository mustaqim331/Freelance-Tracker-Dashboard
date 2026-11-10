# Freelance Analytics & Target Dashboard (Python)

A local Flask + SQLite conversion of the supplied Google Apps Script dashboard.
It does not use Gemini, Google Apps Script, Google Sheets, or any vision API.

## Features

- Earnings and hours dashboard with weekly, monthly, and daily targets
- Daily recording breakdown and Chart.js visualisations
- Task/timetable planner and task status toggling
- Multiple screenshot upload using local Tesseract OCR + OpenCV
- Per-image results with partial success when an image cannot be processed
- Duplicate recording detection by recording ID
- SQLite persistence in `instance/dashboard.db`

## Requirements

- Python 3.10+
- Tesseract OCR installed separately
- Windows, macOS, or Linux

### Install Tesseract

**Windows:** Install from https://github.com/UB-Mannheim/tesseract/wiki

If Tesseract is not detected automatically, open `ocr_parser.py` and uncomment
`pytesseract.pytesseract.tesseract_cmd`, setting it to your installation path.

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install tesseract-ocr
```

**macOS:**
```bash
brew install tesseract
```

## Setup

### Windows PowerShell
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

If PowerShell blocks activation, use Command Prompt:
```cmd
.venv\Scripts\activate.bat
pip install -r requirements.txt
python app.py
```

### macOS / Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

## Screenshot OCR notes

Select multiple screenshots in the upload field to process them together. Each
image can be up to 15 MB, with a 60 MB maximum for a single upload request.
OCR is local and free, but unlike a vision-language model it recognises text;
it does not understand arbitrary screen layouts. The parser currently expects
each recording's timestamp/ID, room name, and duration to appear on the same
or nearby OCR lines. It recognises the room names configured in
`ocr_parser.py`. Add room labels there if your screenshot uses different names.

The parser deliberately skips incomplete rows instead of inventing missing
values. For best results:
- Upload a clear screenshot, not a photo of a screen.
- Avoid cropping off the date, room, or duration columns.
- Use high-resolution PNG/JPG where possible.
- Check the detected and added counts after each upload.

For higher accuracy on complex tables, the next step is to use OCR word
coordinates to group text into visual rows and add a review-before-save screen.

## Data and backup

All data is stored locally in `instance/dashboard.db`.
Stop the app and copy that file to back it up. Do not delete it unless you
intend to reset the database.

## API endpoints

- `GET /api/ping`
- `GET /api/dashboard`
- `POST /api/settings`
- `POST /api/upload` (multipart field: `image`, repeated for each image)
- `GET /api/tasks`
- `POST /api/tasks`
- `POST /api/tasks/<id>/toggle`

## Notes

The dashboard date range retains the supplied script's start date of
1 November 2026. The hourly recording rate defaults to RM20.
Run with `debug=True` only for local development; disable debug mode before
exposing the app to a network.
