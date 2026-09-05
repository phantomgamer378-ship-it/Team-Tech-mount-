"""
Adaptive liveness endpoints (§9, §ADAPTIVE LIVENESS):
POST /api/liveness/start  — issue the (fixed-phrase, prototype) challenge
POST /api/liveness/verify — check the response → PASSED / SUSPICIOUS / FAILED

Tiers: challenges are only REQUIRED for HIGH (70–84, "CHALLENGE") and
CRITICAL (≥85, "MANDATORY") risk — see policy_engine.liveness_decision.
Outcomes are persisted to liveness_sessions. PROTOTYPE honesty: text-match
only; it does NOT defeat cloning (§9) — say so to judges.
"""
from typing import Union

from fastapi import APIRouter, Request

from app.database import database as db
from app.models.schemas import (
    FallbackResponse,
    LivenessStartRequest,
    LivenessStartResponse,
    LivenessVerifyRequest,
    LivenessVerifyResponse,
)
from app.risk.policy_engine import liveness_decision

router = APIRouter(prefix="/api/liveness", tags=["liveness"])


@router.post("/start", response_model=LivenessStartResponse)
def start(request: Request, body: LivenessStartRequest) -> LivenessStartResponse:
    """Issue a challenge for a session. The tier decision lives with the
    analysis pipeline; this endpoint lets the UI (re)start one explicitly."""
    started = request.app.state.services.liveness_service.start_challenge(body.session_id)
    db.save_liveness(body.session_id, started["challenge"])
    return LivenessStartResponse(**started)


@router.post("/verify", response_model=Union[LivenessVerifyResponse, FallbackResponse])
def verify(request: Request, body: LivenessVerifyRequest):
    """Verify the spoken response. A FAILED/SUSPICIOUS outcome should push the
    final risk up (liveness inside the decision loop) — that final-risk update
    is wired at the pipeline level when the UI sends the follow-up analysis."""
    result = request.app.state.services.liveness_service.verify(
        body.session_id, spoken_text=body.spoken_text
    )
    # Persist only real outcomes — the "no challenge" FAILED has nothing to update.
    if "No challenge started" not in (result.get("note") or ""):
        db.update_liveness_status(body.session_id, result["status"])
    return result
