"""
POST /api/analyze/audio (§12/§13) — multipart upload → full pipeline → the
canonical AnalysisResponse (or the fallback shape).

Route responsibilities ONLY (the intelligence lives in app/pipeline.py):
  * validate upload (type, size — settings.MAX_UPLOAD_MB);
  * hold the audio in a TEMP file and DELETE it right after analysis
    (privacy_mode: raw audio is never persisted, §PRIVACY-FIRST);
  * persist the RESULT (metadata + scores) via the database layer;
  * never leak a raw exception — every response fits the frozen contract.
"""
import os
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Union

from fastapi import APIRouter, File, Form, Request, UploadFile

from app.config import settings
from app.database import database as db
from app.models.schemas import AnalysisResponse, FallbackResponse
from app.pipeline import analyze_audio

router = APIRouter(prefix="/api", tags=["analyze"])

ALLOWED_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".aiff", ".aif"}


def _fallback(error: str) -> FallbackResponse:
    return FallbackResponse(error=error)


@router.post("/analyze/audio", response_model=Union[AnalysisResponse, FallbackResponse])
def analyze_audio_endpoint(
    request: Request,
    file: UploadFile = File(...),
    lang: str = Form("hi"),
    session_id: Optional[str] = Form(None),
):
    services = request.app.state.services

    # --- upload validation -------------------------------------------------
    suffix = Path(file.filename or "audio.wav").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        return _fallback(
            f"Unsupported audio type '{suffix}'. Supported: {sorted(ALLOWED_SUFFIXES)}"
        )
    if lang not in ("hi", "mr"):
        return _fallback(f"lang must be 'hi' or 'mr' (prototype targets), got '{lang}'")

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    chunks, size = [], 0
    while True:
        chunk = file.file.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > max_bytes:
            return _fallback(
                f"File too large: >{settings.MAX_UPLOAD_MB} MB (§PRIVACY/§SECURITY)"
            )
        chunks.append(chunk)
    if size == 0:
        return _fallback("Empty upload")

    # --- session -----------------------------------------------------------
    sid = (session_id or "").strip() or uuid.uuid4().hex[:12]

    # --- analyse (audio lives ONLY in a temp file, deleted right after) ----
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(b"".join(chunks))
        tmp.close()
        result = analyze_audio(
            services,
            audio_path=tmp.name,
            session_id=sid,
            lang=lang,
            source_hint=file.filename or "",
        )
    finally:
        try:
            os.unlink(tmp.name)  # PRIVACY-FIRST: never persist raw audio
        except OSError:
            pass

    response = result["response"]

    # --- persist the RESULT (never the audio) ------------------------------
    if response.get("risk") is not None:
        db.create_session(sid, source="upload")
        db.save_analysis_result(sid, response)
        lv = response.get("liveness") or {}
        if lv.get("required") and lv.get("challenge"):
            db.save_liveness(sid, lv["challenge"])

    return response
