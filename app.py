from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import os
import httpx


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Khutbah Translator")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class TranslationRequest(BaseModel):
    arabic: str


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/health")
async def health():
    return {"status": "ok", "service": "khutbah-translator"}


@app.post("/upload")
async def upload_audio(audio: UploadFile = File(...)):
    suffix = Path(audio.filename or "audio").suffix.lower() or ".bin"
    destination = UPLOAD_DIR / f"{uuid4().hex}{suffix.replace(' ', '')}"
    with destination.open("wb") as output:
        while chunk := await audio.read(1024 * 1024):
            output.write(chunk)
    return JSONResponse({"status": "received", "filename": destination.name})


@app.post("/translate")
async def translate(request: TranslationRequest):
    endpoint = os.getenv("LIBRETRANSLATE_URL", "http://127.0.0.1:5000").rstrip("/")
    payload = {
        "q": request.arabic,
        "source": "ar",
        "target": "en",
        "format": "text",
    }
    api_key = os.getenv("LIBRETRANSLATE_API_KEY")
    if api_key:
        payload["api_key"] = api_key
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(f"{endpoint}/translate", json=payload)
        response.raise_for_status()
    result = response.json()
    return {"arabic": request.arabic, "english": result["translatedText"]}
