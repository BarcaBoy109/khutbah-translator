# Khutbah Translator

Khutbah Translator is a live Arabic-to-English translation companion for Friday sermons.

## Current status

This is an early prototype. Browser speech recognition captures Arabic, and the backend sends finalized segments to a configurable LibreTranslate server. Qur’an and hadith passages are flagged for verification and should be matched against approved source translations.

## Requirements

- Python 3.11+
- Node.js 20+ for smoke tests
- A browser with Web Speech API support
- LibreTranslate, locally or hosted

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

In a separate terminal, start local LibreTranslate:

```powershell
pip install libretranslate
libretranslate
```

Start KhutbahT:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --reload
```

Open http://127.0.0.1:8000.

## Configuration

Set these environment variables or copy `.env.example` to `.env`:

```text
LIBRETRANSLATE_URL=http://127.0.0.1:5000
LIBRETRANSLATE_API_KEY=
```

For hosted LibreTranslate, change the URL and add its API key if required. Keep the key on the server; never put it in the frontend.

## Deploy on Render

Create a Render Web Service connected to this repository:

```text
Build command: pip install -r requirements.txt
Start command: uvicorn app:app --host 0.0.0.0 --port $PORT
```

Set:

```text
LIBRETRANSLATE_URL=https://libretranslate.com
LIBRETRANSLATE_API_KEY=<your-provider-key>
```

Render’s free plan is suitable for an MVP but may sleep when idle. Audio uploads are currently stored locally and should move to object storage before production use.

## Tests

```powershell
npm test
.\.venv\Scripts\python.exe -m py_compile app.py
```

## Project structure

```text
app.py                         FastAPI application
templates/index.html           Translation interface
tests/fixtures/                Arabic sermon evaluation samples
tests/smoke.test.mjs           Node smoke tests
requirements.txt               Python dependencies
Dockerfile                     Container deployment setup
```

## License

No license has been selected yet. Add one before accepting external contributions or distributing the project.
