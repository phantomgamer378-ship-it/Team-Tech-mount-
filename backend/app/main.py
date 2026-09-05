"""
Voice Clone Shield — FastAPI entrypoint (Phase 1 skeleton).

Run from backend/ (see README for full setup):
    source .venv/bin/activate
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

Interactive API docs once running:  http://localhost:8000/docs

PROTOTYPE vs FUTURE PRODUCT (§1–2): this backend currently exposes only
/ and /api/health. The real AI models (AASIST-L voice anti-spoofing,
IndicConformer ASR), analyze endpoints, WebSocket streaming and the SQLite
database arrive in Phases 2–9. Nothing here is production-ready.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.audio import router as audio_router
from app.api.liveness import router as liveness_router
from app.api.session import router as session_router
from app.config import settings
from app.database import database as db
from app.services import ServiceContainer
from app.utils.logging_setup import setup_logging

log = logging.getLogger("main")


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup/shutdown hook — models are loaded ONCE here (§19), never per-request."""
    setup_logging()
    log.info(
        "Starting %s v%s | DEMO_MODE=%s | PRIVACY_MODE=%s | DEVICE=%s",
        settings.APP_NAME, settings.VERSION,
        settings.DEMO_MODE, settings.PRIVACY_MODE, settings.DEVICE,
    )
    application.state.services.load_all()
    db.init_db()  # SQLite tables — created once at startup, never per request
    log.info("Startup complete — try /api/health or /docs")
    yield
    log.info("Shutting down %s", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description=(
        "PROTOTYPE: AI voice-clone scam shield (internal SIH round). "
        "Works on recorded/uploaded/mic audio — NOT a production call-security system."
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

# Services created once at import; real model weights load inside lifespan()
# (§19). USE_DEMO_SERVICES=true swaps in the app/demo/* mocks instead.
app.state.services = ServiceContainer.create()

app.include_router(health_router)
app.include_router(session_router)
app.include_router(audio_router)
app.include_router(liveness_router)


@app.get("/", tags=["meta"])
def root():
    """Friendly landing so a browser visit to the server isn't a 404."""
    return {
        "app": settings.APP_NAME,
        "version": settings.VERSION,
        "status": "PROTOTYPE",
        "health": "/api/health",
        "docs": "/docs",
    }
