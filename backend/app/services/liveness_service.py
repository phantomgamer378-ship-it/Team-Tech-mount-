"""
LivenessService — challenge-response for HIGH-risk calls (§9, Phase 7).

Flow: start_challenge() → response capture → verify() → LIVE / SUSPICIOUS / FAILED.

PROTOTYPE honesty (§9): the naive text match below does NOT defeat
sophisticated voice cloning — a cloned voice that repeats the phrase still
passes. This layer is a placeholder for a real challenge-response speaker
verification system. Say this out loud to judges.
"""
import logging
import random
import time
from typing import Dict, Optional

log = logging.getLogger(__name__)

CHALLENGE_WORDS = ["Blue", "Tiger", "River", "Falcon", "Monsoon", "Copper", "Sunrise", "Banyan"]
CHALLENGE_EXPIRY_SEC = 60

class LivenessService:
    has_model = False  # stateless — reported in /api/health

    def __init__(self) -> None:
        # PROTOTYPE: in-memory store, lost on restart. Production would persist
        # challenges server-side with expiry (§17 tables).
        self._challenges: Dict[str, Dict] = {}

    def start_challenge(self, session_id: str) -> dict:
        """Generate a random speakable phrase, e.g. 'Blue Tiger 47' (§9)."""
        phrase = f"{' '.join(random.sample(CHALLENGE_WORDS, 2))} {random.randint(10, 99)}"
        self._challenges[session_id] = {
            "challenge": phrase, 
            "status": "PENDING",
            "created_at": time.time()
        }
        log.info("Liveness challenge started for session=%s", session_id)
        return {
            "session_id": session_id,
            "required": True,
            "status": "PENDING",
            "challenge": phrase,
        }

    def verify(self, session_id: str, spoken_text: Optional[str] = None) -> dict:
        """
        Phase 7 hook. PROTOTYPE check: naive case-insensitive text compare only.
        Enforces expiry and single-use logic.
        """
        record = self._challenges.pop(session_id, None)  # Single-use: always remove the record
        
        if not record:
            return {
                "session_id": session_id,
                "status": "FAILED",
                "note": "No challenge started for this session or challenge was already used.",
            }

        # Check expiry
        if time.time() - record["created_at"] > CHALLENGE_EXPIRY_SEC:
            return {
                "session_id": session_id,
                "status": "SUSPICIOUS",
                "challenge": record["challenge"],
                "note": "Challenge expired.",
            }

        if spoken_text and spoken_text.strip().lower() == record["challenge"].lower():
            status = "LIVE"
        else:
            status = "SUSPICIOUS"

        return {
            "session_id": session_id,
            "status": status,
            "challenge": record["challenge"],
            "note": (
                "PROTOTYPE check — text match only; a cloned voice repeating the "
                "phrase still passes. Real speaker verification is a future phase (§9)."
            ),
        }
