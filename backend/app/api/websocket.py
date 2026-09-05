"""
WebSocket endpoint — simulated real-time audio streaming (Phase 9, §15).

Protocol:
  1. Client opens WS /ws/session/{session_id}
  2. Client sends 1 s PCM chunks as binary messages (float32, mono, 16 kHz)
     OR base64-encoded JSON: {"type": "audio_chunk", "data": "<base64>", "index": N}
  3. Server replies with progressive JSON status after each chunk
  4. Client sends {"type": "end"} → server replies with the final analysis card
  5. Either side may close the connection

PROTOTYPE vs FUTURE PRODUCT (§15):
  * Not true streaming inference — each chunk is buffered, then the full
    accumulated audio is run through the pipeline at the end.
  * Chunk-level risk "progression" is simulated (voice detector re-runs on
    accumulated audio for realism, but it's NOT real frame-level inference).
  * A production system would do actual streaming ASR + incremental risk
    updates via WebRTC data channels.
"""
import asyncio
import base64
import json
import logging
import uuid
from typing import Dict, List, Optional

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings

log = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

# In-memory session store — PROTOTYPE only (§17: production → DB)
_active_sessions: Dict[str, dict] = {}


@router.websocket("/ws/session/{session_id}")
async def audio_stream(ws: WebSocket, session_id: str):
    """
    Accept a WebSocket connection for real-time audio analysis.

    The client (Flutter app or browser WebRTC bridge) streams 1 s chunks.
    The server accumulates them and sends back progressive analysis.
    """
    await ws.accept()
    log.info("WS session %s: connected", session_id)

    session = {
        "id": session_id,
        "chunks": [],
        "chunk_count": 0,
        "status": "CONNECTED",
        "accumulated_duration_s": 0.0,
    }
    _active_sessions[session_id] = session

    try:
        await ws.send_json({
            "type": "session_start",
            "session_id": session_id,
            "status": "CONNECTED",
            "message": "Send audio chunks (float32 binary or base64 JSON). Send {\"type\": \"end\"} when done.",
        })

        while True:
            raw = await ws.receive()

            # --- binary frame: raw float32 PCM ---
            if "bytes" in raw and raw["bytes"]:
                chunk = _bytes_to_array(raw["bytes"])
                if chunk is None:
                    await ws.send_json({"type": "error", "message": "Invalid binary audio data"})
                    continue
                session["chunks"].append(chunk)
                session["chunk_count"] += 1
                session["accumulated_duration_s"] += len(chunk) / 16000.0
                await _send_chunk_ack(ws, session)

            # --- text frame: JSON message ---
            elif "text" in raw and raw["text"]:
                try:
                    msg = json.loads(raw["text"])
                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "message": "Invalid JSON"})
                    continue

                msg_type = msg.get("type", "")

                if msg_type == "audio_chunk":
                    chunk = _decode_base64_chunk(msg.get("data"))
                    if chunk is None:
                        await ws.send_json({"type": "error", "message": "Invalid base64 audio"})
                        continue
                    session["chunks"].append(chunk)
                    session["chunk_count"] += 1
                    session["accumulated_duration_s"] += len(chunk) / 16000.0
                    await _send_chunk_ack(ws, session)

                elif msg_type == "end":
                    result = await _run_final_analysis(ws, session)
                    await ws.send_json(result)
                    break

                elif msg_type == "ping":
                    await ws.send_json({"type": "pong", "session_id": session_id})

                else:
                    await ws.send_json({
                        "type": "error",
                        "message": f"Unknown message type: {msg_type}",
                    })
            else:
                # WebSocket close or empty frame
                break

    except WebSocketDisconnect:
        log.info("WS session %s: client disconnected", session_id)
    except Exception as exc:
        log.warning("WS session %s: unexpected error — %s", session_id, exc)
        try:
            await ws.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        _active_sessions.pop(session_id, None)
        log.info("WS session %s: cleaned up", session_id)


# ------------------------------------------------------------------ helpers

def _bytes_to_array(data: bytes) -> Optional[np.ndarray]:
    """Convert raw bytes (expected float32 PCM at 16 kHz) to a numpy array."""
    try:
        arr = np.frombuffer(data, dtype=np.float32)
        if arr.size == 0:
            return None
        return arr
    except Exception:
        return None


def _decode_base64_chunk(b64_str: Optional[str]) -> Optional[np.ndarray]:
    """Decode base64-encoded float32 PCM bytes."""
    if not b64_str:
        return None
    try:
        raw = base64.b64decode(b64_str)
        return _bytes_to_array(raw)
    except Exception:
        return None


async def _send_chunk_ack(ws: WebSocket, session: dict):
    """Send a progressive status update after each received chunk."""
    await ws.send_json({
        "type": "chunk_ack",
        "session_id": session["id"],
        "chunk_index": session["chunk_count"],
        "accumulated_duration_s": round(session["accumulated_duration_s"], 2),
        "status": "RECEIVING",
    })


async def _run_final_analysis(ws: WebSocket, session: dict) -> dict:
    """
    Run the full analysis pipeline on accumulated audio.

    PROTOTYPE: this is NOT true streaming inference. We concatenate all
    chunks and run the same batch pipeline (Phase 8 style). The WebSocket
    layer just provides the progressive UX.
    """
    await ws.send_json({
        "type": "status",
        "session_id": session["id"],
        "status": "ANALYZING",
        "message": "Processing accumulated audio…",
    })

    chunks: List[np.ndarray] = session.get("chunks", [])
    if not chunks:
        return {
            "type": "analysis_complete",
            "session_id": session["id"],
            "status": "partial",
            "error": "No audio chunks received",
            "fallback_used": True,
        }

    # Concatenate all chunks into one waveform
    waveform = np.concatenate(chunks).astype(np.float32)
    duration_s = round(len(waveform) / 16000.0, 3)

    # Peak-normalize (same logic as AudioProcessor.normalize)
    peak = float(np.max(np.abs(waveform))) if waveform.size else 0.0
    if peak > 0:
        waveform = (waveform / peak).astype(np.float32)

    # --- Run through the service pipeline (import here to avoid circular) ---
    # In Phase 8 wiring, this would use the ServiceContainer from app.state.
    # For the WebSocket endpoint, we import and use services directly.
    from app.services.voice_detector import VoiceDetector
    from app.services.asr_service import ASRService
    from app.services.scam_detector import ScamDetector
    from app.risk.risk_engine import RiskEngine

    voice_detector = VoiceDetector()
    voice_detector.load_model()

    asr = ASRService()
    scam = ScamDetector()
    risk_engine = RiskEngine()

    # Step 1: Voice/deepfake analysis
    await ws.send_json({
        "type": "status",
        "session_id": session["id"],
        "status": "ANALYZING_VOICE",
        "message": "Running deepfake detection…",
    })
    voice_result = voice_detector.predict(waveform)
    await asyncio.sleep(0.1)  # Simulate processing time for UX

    # Step 2: ASR (transcript)
    await ws.send_json({
        "type": "status",
        "session_id": session["id"],
        "status": "TRANSCRIBING",
        "message": "Transcribing audio…",
    })
    asr_result = asr.transcribe(waveform)
    transcript = asr_result.get("transcript", "")
    await asyncio.sleep(0.1)

    # Step 3: Scam analysis on transcript
    await ws.send_json({
        "type": "status",
        "session_id": session["id"],
        "status": "ANALYZING_SCAM",
        "message": "Analyzing for scam patterns…",
    })
    scam_result = scam.analyze(transcript)
    await asyncio.sleep(0.1)

    # Step 4: Risk fusion
    voice_risk = voice_result.get("voice_risk", 0.0)
    scam_risk = scam_result.get("risk", 0.0)
    fused = risk_engine.fuse(voice_risk, scam_risk, context_risk=0.0)

    return {
        "type": "analysis_complete",
        "session_id": session["id"],
        "status": "ok",
        "duration_s": duration_s,
        "chunks_received": session["chunk_count"],
        "voice_analysis": voice_result,
        "transcript": transcript,
        "language": asr_result.get("language"),
        "scam_analysis": scam_result,
        "risk": {
            "score": fused["risk_score"],
            "level": fused["risk_level"],
            "signals": fused["signals"],
        },
        "fallback_used": voice_result.get("note", "").startswith("DEMO MODE")
                         or asr_result.get("note", "").startswith("DEMO MODE"),
        "note": (
            "PROTOTYPE — simulated real-time (buffered chunks, not streaming "
            "inference). WebRTC integration is future phase H (§27)."
        ),
    }
