"""
PolicyEngine — tier → action (§POLICY ENGINE, Phase 10).

Pure function. The Risk Engine asks "how dangerous is this?"; the Policy
Engine asks "what should we do about it?" — the separation matters because
organizations configure different policies (consumer today; bank/enterprise
rules are future work, documented in the master prompt).

PROTOTYPE policy (master prompt):
    LOW      → CONTINUE
    MEDIUM   → CAUTION
    HIGH     → VERIFY_CALLER   (liveness + warning)
    CRITICAL → WARN            (strong warning + recommended prevention)

Fail-safe rule: an UNKNOWN level maps to the most protective action (WARN) —
never fail open. This function must never raise.

Adaptive-liveness decision (§ADAPTIVE LIVENESS, master prompt tiers):
    risk < 40   → NONE       (no challenge)
    40 ≤ r < 70 → MONITOR    (watch, don't challenge)
    70 ≤ r < 85 → CHALLENGE  (challenge offered/considered)
    risk ≥ 85   → MANDATORY  (challenge mandatory)
"""
from typing import Dict

POLICY_ACTIONS: Dict[str, str] = {
    "LOW": "CONTINUE",
    "MEDIUM": "CAUTION",
    "HIGH": "VERIFY_CALLER",
    "CRITICAL": "WARN",
}

_FAIL_SAFE_ACTION = "WARN"


def decide(level: str) -> str:
    """Map a risk level to its policy action (pure, never raises)."""
    return POLICY_ACTIONS.get(level, _FAIL_SAFE_ACTION)


def liveness_decision(risk_score: int) -> Dict:
    """Map a 0–100 risk score to the adaptive-liveness tier (pure, never raises)."""
    if risk_score >= 85:
        return {"tier": "MANDATORY", "required": True}
    if risk_score >= 70:
        return {"tier": "CHALLENGE", "required": True}
    if risk_score >= 40:
        return {"tier": "MONITOR", "required": False}
    return {"tier": "NONE", "required": False}
