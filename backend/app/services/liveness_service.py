"""
LivenessService — challenge-response for HIGH-risk calls (§9, Phase 7).

Flow: start_challenge() → response capture → verify() → PASSED / SUSPICIOUS / FAILED.

PROTOTYPE honesty (§9): the naive text match below does NOT defeat
sophisticated voice cloning — a cloned voice that repeats the phrase still
passes. This layer is a placeholder for a real challenge-response speaker
verification system. Say this out loud to judges.

The challenge phrase is FIXED ("Blue Tiger 47") for the prototype —
per the master prompt (§ADAPTIVE LIVENESS), randomization, replay resistance
and prompt unpredictability are future work. Fixed also keeps demo runs
deterministic (§DEMO RELIABILITY).
"""
import logging
import time
from typing import Dict, Optional

from app.config import settings

log = logging.getLogger(__name__)

# Fixed prototype challenge — NOT randomized (future work, see docstring).
CHALLENGE_PHRASE = "Blue Tiger 47"


class LivenessService:
    has_model = False  # stateless — reported in /api/health

    def __init__(self) -> None:
        # PROTOTYPE: in-memory store, lost on restart. Challenges expire after
        # settings.LIVENESS_EXPIRY_SECONDS (§ADAPTIVE LIVENESS); the
        # liveness_sessions table persists outcomes.
        self._challenges: Dict[str, Dict] = {}

    def start_challenge(self, session_id: str) -> dict:
        """Issue the fixed prototype challenge, e.g. 'Blue Tiger 47' (§9)."""
        self._challenges[session_id] = {
            "challenge": CHALLENGE_PHRASE,
            "status": "PENDING",
            "created": time.time(),
        }
        log.info("Liveness challenge started for session=%s", session_id)
        return {
            "session_id": session_id,
            "required": True,
            "status": "PENDING",
            "challenge": CHALLENGE_PHRASE,
        }

    def verify(self, session_id: str, spoken_text: Optional[str] = None) -> dict:
        """
        Phase 7 hook. PROTOTYPE check: naive case-insensitive text compare only,
        with expiry — a response after settings.LIVENESS_EXPIRY_SECONDS counts
        as FAILED (anti-replay posture; not real anti-replay analysis).

        A real implementation would do speaker verification / anti-spoofing on
        the response audio — that is a future phase, not this prototype (§9).
        """
        record = self._challenges.get(session_id)
        if not record:
            return {
                "session_id": session_id,
                "status": "FAILED",
                "challenge": None,
                "note": "No challenge started for this session",
            }

        if time.time() - record["created"] > settings.LIVENESS_EXPIRY_SECONDS:
            record["status"] = "FAILED"
            return {
                "session_id": session_id,
                "status": "FAILED",
                "challenge": record["challenge"],
                "note": (
                    f"Challenge expired after {settings.LIVENESS_EXPIRY_SECONDS}s "
                    "— responses must be prompt (prototype expiry)."
                ),
            }

        if spoken_text and spoken_text.strip().lower() == record["challenge"].lower():
            record["status"] = "PASSED"   # v3 contract state
        else:
            record["status"] = "SUSPICIOUS"

        return {
            "session_id": session_id,
            "status": record["status"],
            "challenge": record["challenge"],
            "note": (
                "PROTOTYPE check — text match against a fixed phrase only; a "
                "cloned voice repeating the phrase still passes. Randomized, "
                "replay-resistant challenges + speaker verification are future "
                "work (§9)."
            ),
        }
