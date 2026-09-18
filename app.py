from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from openai import AsyncOpenAI
import os


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Khutbah Live Translator")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class TranslationRequest(BaseModel):
    arabic: str


def get_openai_client() -> AsyncOpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    return AsyncOpenAI(api_key=api_key)


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
    client = get_openai_client()
    response = await client.responses.create(
        model=os.getenv("OPENAI_TRANSLATION_MODEL", "gpt-5-mini"),
        instructions=(
            "Translate Arabic Friday sermon speech into clear, faithful English. "
            "Preserve Islamic terms, names, quotations, and attribution. "
            "Return only the English translation; do not add commentary."
        ),
        input=request.arabic,
    )
    return {"arabic": request.arabic, "english": response.output_text}
