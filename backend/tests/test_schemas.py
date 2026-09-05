"""
Phase 2 tests — the frozen v3 contract (models/schemas.py).

The contract is the single source of truth for Codex's API layer and
Antigravity's Flutter screens; these tests guard its exact shapes.

Run from backend/:  python -m pytest -v
"""
import pytest
from pydantic import ValidationError

from app.models.schemas import (
    AnalysisResponse,
    FallbackResponse,
    RiskAssessment,
)


# The canonical success example from the master prompt, verbatim fields.
CANONICAL = {
    "session_id": "demo-001",
    "status": "complete",
    "audio": {"duration": 23.4, "language": "mr"},
    "voice_trust": {
        "spoof_risk": 0.91,
        "speaker_mismatch_risk": 0.72,
        "overall_voice_risk": 0.84,
        "status": "SUSPICIOUS",
    },
    "asr": {"language": "mr", "transcript": "...", "segments": []},
    "scam_analysis": {
        "risk": 0.88,
        "category": "Bank/KYC Fraud",
        "indicators": ["Urgency", "OTP request"],
    },
    "attack_types": ["AI Voice Impersonation", "Bank Fraud"],
    "risk": {"score": 91, "level": "HIGH"},
    "liveness": {"required": True, "status": "PENDING"},
    "explanation": [
        "[voice] Synthetic voice evidence detected",
        "[scam_rule] Urgent financial request detected",
    ],
    "recommendation": "Do not share OTP or transfer money.",
}


def test_canonical_response_validates():
    model = AnalysisResponse(**CANONICAL)
    assert model.risk.level == "HIGH"
    assert model.voice_trust.spoof_risk == 0.91
    assert model.attack_types == ["AI Voice Impersonation", "Bank Fraud"]


def test_minimal_response_validates():
    """Every field except session_id is optional — early pipelines still fit."""
    model = AnalysisResponse(session_id="s1")
    assert model.status == "complete"
    assert model.risk_timeline == []
    assert model.fallback_used is False


def test_risk_timeline_entries_validate():
    model = AnalysisResponse(
        session_id="s1",
        risk_timeline=[
            {"t": 1.0, "risk_score": 12, "level": "LOW"},
            {"t": 2.0, "voice_risk": 0.8, "scam_risk": 0.5, "risk_score": 57, "level": "HIGH"},
        ],
    )
    assert model.risk_timeline[1].level == "HIGH"


def test_invalid_risk_level_rejected():
    with pytest.raises(ValidationError):
        RiskAssessment(score=91, level="EXTREME")


def test_old_liveness_state_rejected():
    """'LIVE' was the v2 state name — the v3 contract uses PASSED. This test
    fails if anyone regresses the states."""
    with pytest.raises(ValidationError):
        AnalysisResponse(session_id="s1", liveness={"required": True, "status": "LIVE"})


def test_out_of_range_scores_rejected():
    with pytest.raises(ValidationError):
        AnalysisResponse(session_id="s1", voice_trust={"spoof_risk": 1.5})
    with pytest.raises(ValidationError):
        RiskAssessment(score=140, level="HIGH")


def test_fallback_shape_validates():
    fb = FallbackResponse(error="Voice model unavailable")
    dumped = fb.model_dump()
    assert dumped == {
        "status": "partial",
        "error": "Voice model unavailable",
        "fallback_used": True,
    }


def test_fallback_shape_is_exactly_three_fields():
    """The frozen fallback shape has exactly three keys — no more, no less."""
    assert set(FallbackResponse.model_fields.keys()) == {"status", "error", "fallback_used"}
