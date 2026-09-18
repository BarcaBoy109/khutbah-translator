from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Khutbah Live Translator")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


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
