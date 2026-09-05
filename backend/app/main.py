"""
Voice Clone Shield — FastAPI entrypoint.

Run from backend/ (see README for full setup):
    source .venv/bin/activate
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

Interactive API docs once running:  http://localhost:8000/docs

Endpoints available:
  GET  /api/health                — service status
  POST /api/analyze/audio         — upload + full pipeline (Phase 8)
  POST /api/liveness/start        — start liveness challenge (§9)
  POST /api/liveness/verify       — verify liveness response (§9)
  WS   /ws/session/{id}           — real-time audio streaming (Phase 9)
  WS   /ws/webrtc/signal/{id}     — WebRTC signaling relay (Phase H)
  GET  /webrtc/                   — browser WebRTC audio capture demo

PROTOTYPE vs FUTURE PRODUCT (§1–2): this is a hackathon demo, not a
production call-security system.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.health import router as health_router
from app.api.analyze import router as analyze_router
from app.api.liveness import router as liveness_router
from app.api.websocket import router as ws_router
from app.api.webrtc import router as webrtc_router
from app.config import settings
from app.services import ServiceContainer
from app.utils.logging_setup import setup_logging

log = logging.getLogger("main")

# Path to the WebRTC browser demo
WEBRTC_DEMO_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "webrtc_demo"


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup/shutdown hook — models are loaded ONCE here (§19), never per-request."""
    setup_logging()
    log.info(
        "Starting %s v%s | DEMO_MODE=%s | DEVICE=%s",
        settings.APP_NAME, settings.VERSION, settings.DEMO_MODE, settings.DEVICE,
    )
    application.state.services.load_all()
    log.info("Startup complete — try /api/health, /docs, or /webrtc/")
    yield
    log.info("Shutting down %s", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description=(
        "PROTOTYPE: AI voice-clone scam shield (internal SIH round). "
        "Works on recorded/uploaded/mic audio — NOT a production call-security system. "
        "Includes WebSocket streaming (Phase 9) and WebRTC audio capture (Phase H)."
    ),
    lifespan=lifespan,
)

# CORS (§12) — permissive ON PURPOSE for the prototype, so the Flutter app on a
# phone / emulator / browser can call this API during the hackathon.
# PROTOTYPE-ONLY: lock allow_origins down to the real frontend origin before
# any deployment outside a demo laptop.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Placeholder services created once at import (cheap — they load no weights).
# Real model weights get loaded inside lifespan() in Phases 3–4 (§19).
app.state.services = ServiceContainer()

# --- HTTP routers ---
app.include_router(health_router)
app.include_router(analyze_router)
app.include_router(liveness_router)

# --- WebSocket routers ---
app.include_router(ws_router)
app.include_router(webrtc_router)

# --- Serve the WebRTC browser demo at /webrtc/ ---
if WEBRTC_DEMO_DIR.is_dir():
    app.mount("/webrtc", StaticFiles(directory=str(WEBRTC_DEMO_DIR), html=True), name="webrtc_demo")


@app.get("/", tags=["meta"])
def root():
    """Friendly landing so a browser visit to the server isn't a 404."""
    return {
        "app": settings.APP_NAME,
        "version": settings.VERSION,
        "status": "PROTOTYPE",
        "health": "/api/health",
        "docs": "/docs",
        "webrtc_demo": "/webrtc/",
        "endpoints": {
            "analyze_audio": "POST /api/analyze/audio",
            "liveness_start": "POST /api/liveness/start",
            "liveness_verify": "POST /api/liveness/verify",
            "ws_audio_stream": "WS /ws/session/{session_id}",
            "ws_webrtc_signal": "WS /ws/webrtc/signal/{session_id}",
        },
    }
