"""
Session + history routes (§12, §17): POST /api/session, GET /api/history,
GET /api/session/{id}.

GET responses that find nothing return the fallback shape (never a raw 404
stack) — every response matches one of the two frozen contract shapes.
"""
import uuid

from fastapi import APIRouter

from app.database import database as db
from app.models.schemas import (
    FallbackResponse,
    HistoryResponse,
    SessionCreateRequest,
    SessionResponse,
)

router = APIRouter(prefix="/api", tags=["session"])


@router.post("/session", response_model=SessionResponse)
def create_session(body: SessionCreateRequest) -> SessionResponse:
    """Create an analysis session. Call this first (or let /analyze/audio
    create one implicitly from the form field)."""
    session_id = uuid.uuid4().hex[:12]
    created = db.create_session(session_id, source=body.source)
    return SessionResponse(session_id=session_id, created_at=created, source=body.source)


@router.get("/history", response_model=HistoryResponse)
def history(limit: int = 20) -> HistoryResponse:
    """Recent analysis results, newest first — metadata + scores only
    (privacy: raw audio is never persisted, §PRIVACY-FIRST)."""
    limit = max(1, min(limit, 100))
    items = db.get_history(limit=limit)
    return HistoryResponse(history=items, count=len(items))


@router.get("/session/{session_id}")
def get_session(session_id: str):
    """One session + its analysis results, or the fallback shape if unknown."""
    data = db.get_session(session_id)
    if data is None:
        return FallbackResponse(error=f"Session not found: {session_id}")
    return data
