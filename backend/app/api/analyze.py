"""
Audio analysis endpoint — POST /api/analyze/audio (Phase 8, §12/§13).

Accepts a multipart audio file upload, runs the full pipeline:
    preprocess → voice detector → ASR → scam detector → risk fusion
    → optional liveness challenge (HIGH only)

Returns the §13 AnalysisResponse contract.

PROTOTYPE vs FUTURE PRODUCT:
  * Single-file upload only (no streaming). Phase 9 WebSocket adds
    progressive chunk-based analysis.
  * No raw audio retention beyond the request (§23: privacy).
  * Max upload size enforced via MAX_UPLOAD_MB env var.
"""
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import JSONResponse

from app.config import settings
from app.models.schemas import AnalysisResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["analyze"])

# Allowed MIME types for audio uploads
ALLOWED_TYPES = {
    "audio/wav", "audio/x-wav", "audio/wave",
    "audio/flac", "audio/x-flac",
    "audio/ogg", "audio/vorbis",
    "audio/mpeg", "audio/mp3",
    "audio/aiff", "audio/x-aiff",
    "application/octet-stream",  # browser often sends this for wav
}


@router.post("/analyze/audio", response_model=AnalysisResponse)
async def analyze_audio(
    request: Request,
    audio: UploadFile = File(..., description="Audio file (WAV/FLAC/OGG/MP3/AIFF)"),
    language: Optional[str] = None,
):
    """
    Full §13 analysis pipeline for an uploaded audio file.

    Returns AnalysisResponse with voice_analysis, transcript, scam_analysis,
    risk assessment, and optional liveness challenge trigger.
    """
    session_id = str(uuid.uuid4())[:12]
    services = getattr(request.app.state, "services", None)

    if services is None:
        return AnalysisResponse(
            session_id=session_id,
            status="partial",
            error="Services not initialized",
            fallback_used=True,
        )

    # --- 1. VALIDATE upload ---
    content_type = audio.content_type or "application/octet-stream"
    if content_type not in ALLOWED_TYPES:
        log.warning("Rejected upload: content_type=%s", content_type)
        # Don't hard-reject; some browsers send wrong types. Proceed and
        # let the audio processor decide (§20: resilience over strictness).

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    content = await audio.read()
    if len(content) > max_bytes:
        return AnalysisResponse(
            session_id=session_id,
            status="partial",
            error=f"File too large: {len(content) / 1024 / 1024:.1f} MB (max {settings.MAX_UPLOAD_MB} MB)",
            fallback_used=True,
        )
    if len(content) == 0:
        return AnalysisResponse(
            session_id=session_id,
            status="partial",
            error="Empty file uploaded",
            fallback_used=True,
        )

    # --- 2. SAVE to temp file (§23: deleted after processing) ---
    suffix = Path(audio.filename or "upload.wav").suffix or ".wav"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(content)
        tmp.flush()
        tmp.close()
        tmp_path = Path(tmp.name)

        # --- 3. PREPROCESS ---
        prep = services.audio_processor.preprocess(tmp_path)
        if not prep.get("ok"):
            return AnalysisResponse(
                session_id=session_id,
                status="partial",
                error=prep.get("error", "Audio preprocessing failed"),
                fallback_used=True,
            )

        waveform = prep["waveform"]

        # --- 4. VOICE DETECTION ---
        voice_result = services.voice_detector.predict(waveform)

        # --- 5. ASR (transcript) ---
        asr_result = services.asr_service.transcribe(waveform, language=language)
        transcript = asr_result.get("transcript", "")

        # --- 6. SCAM ANALYSIS ---
        scam_result = services.scam_detector.analyze(transcript)

        # --- 7. RISK FUSION ---
        voice_risk = voice_result.get("voice_risk", 0.0)
        scam_risk = scam_result.get("risk", 0.0)
        fused = services.risk_engine.fuse(voice_risk, scam_risk, context_risk=0.0)

        # --- 8. LIVENESS (HIGH risk only, §9) ---
        liveness = None
        if fused["risk_level"] == "HIGH":
            liveness_data = services.liveness_service.start_challenge(session_id)
            from app.models.schemas import LivenessInfo
            liveness = LivenessInfo(
                required=True,
                status=liveness_data["status"],
                challenge=liveness_data.get("challenge"),
            )

        # --- 9. BUILD RESPONSE ---
        from app.models.schemas import (
            VoiceAnalysis, ScamAnalysis, RiskAssessment,
        )

        fallback_used = (
            voice_result.get("note", "").startswith("DEMO MODE")
            or asr_result.get("note", "").startswith("DEMO MODE")
        )

        recommendation = _generate_recommendation(fused["risk_level"], fallback_used)

        return AnalysisResponse(
            session_id=session_id,
            status="ok",
            language=asr_result.get("language", language),
            transcript=transcript if transcript else None,
            voice_analysis=VoiceAnalysis(
                ai_voice=voice_result.get("ai_voice", False),
                risk=voice_result.get("voice_risk", 0.0),
                confidence=voice_result.get("confidence", 0.0),
                model=voice_result.get("model"),
                note=voice_result.get("note"),
            ),
            scam_analysis=ScamAnalysis(
                risk=scam_result.get("risk", 0.0),
                category=scam_result.get("category", "Unknown"),
                indicators=scam_result.get("indicators", []),
            ),
            risk=RiskAssessment(
                score=fused["risk_score"],
                level=fused["risk_level"],
                signals=fused["signals"],
            ),
            liveness=liveness,
            recommendation=recommendation,
            fallback_used=fallback_used,
        )

    except Exception as exc:
        log.exception("analyze_audio failed for session %s", session_id)
        return AnalysisResponse(
            session_id=session_id,
            status="partial",
            error=f"Analysis failed: {exc}",
            fallback_used=True,
        )
    finally:
        # §23 — no raw audio retention beyond the request
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


def _generate_recommendation(risk_level: str, fallback_used: bool) -> str:
    """Human-readable recommendation based on risk level."""
    prefix = "[PROTOTYPE — some signals are demo-mode] " if fallback_used else ""

    if risk_level == "HIGH":
        return prefix + (
            "⚠️ HIGH RISK — This audio shows strong indicators of AI voice cloning "
            "and/or scam patterns. Do NOT share personal/financial information. "
            "Verify the caller's identity through a separate, trusted channel."
        )
    elif risk_level == "MEDIUM":
        return prefix + (
            "⚡ MEDIUM RISK — Some suspicious signals detected. Exercise caution. "
            "Verify the caller before sharing any sensitive information."
        )
    else:
        return prefix + (
            "✅ LOW RISK — No strong indicators of voice cloning or scam patterns. "
            "Standard caution still applies."
        )
