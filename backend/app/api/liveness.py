"""
Liveness API endpoints — POST /api/liveness/start + /api/liveness/verify (Phase 8, §9).

Wires the existing LivenessService (Phase 7) into HTTP endpoints so the
Flutter app can trigger and resolve liveness challenges for HIGH-risk sessions.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/liveness", tags=["liveness"])


class LivenessStartRequest(BaseModel):
    session_id: str


class LivenessVerifyRequest(BaseModel):
    session_id: str
    spoken_text: Optional[str] = None


@router.post("/start")
def liveness_start(body: LivenessStartRequest, request: Request):
    """
    Start a liveness challenge for a session (§9).

    Typically called automatically when risk_level == HIGH, but can
    also be triggered manually from the Flutter dashboard.
    """
    services = getattr(request.app.state, "services", None)
    if services is None:
        return {"error": "Services not initialized", "status": "FAILED"}
    return services.liveness_service.start_challenge(body.session_id)


@router.post("/verify")
def liveness_verify(body: LivenessVerifyRequest, request: Request):
    """
    Verify a liveness challenge response (§9).

    PROTOTYPE: naive text match. A real implementation would verify
    the speaker's voice biometrics against the challenge audio.
    """
    services = getattr(request.app.state, "services", None)
    if services is None:
        return {"error": "Services not initialized", "status": "FAILED"}
    return services.liveness_service.verify(body.session_id, body.spoken_text)
