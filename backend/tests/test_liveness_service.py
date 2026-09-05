"""
Phase 11 tests — liveness tiering (policy) + challenge expiry + states.

Run from backend/:  python -m pytest -v
"""
import pytest

from app.config import settings
from app.risk.policy_engine import liveness_decision
from app.services.liveness_service import CHALLENGE_PHRASE, LivenessService


# ------------------------------------------------------- adaptive tiers (§9)

@pytest.mark.parametrize("score,tier,required", [
    (0, "NONE", False), (39, "NONE", False),
    (40, "MONITOR", False), (69, "MONITOR", False),
    (70, "CHALLENGE", True), (84, "CHALLENGE", True),
    (85, "MANDATORY", True), (100, "MANDATORY", True),
])
def test_liveness_tier_boundaries(score, tier, required):
    d = liveness_decision(score)
    assert d == {"tier": tier, "required": required}


# ------------------------------------------------------- states + expiry

@pytest.fixture
def svc():
    return LivenessService()


def test_start_then_correct_phrase_passes(svc):
    started = svc.start_challenge("s1")
    assert started["challenge"] == CHALLENGE_PHRASE      # fixed prototype phrase
    out = svc.verify("s1", spoken_text=CHALLENGE_PHRASE)
    assert out["status"] == "PASSED"


def test_wrong_phrase_is_suspicious(svc):
    svc.start_challenge("s1")
    out = svc.verify("s1", spoken_text="hello world")
    assert out["status"] == "SUSPICIOUS"


def test_case_insensitive_match(svc):
    svc.start_challenge("s1")
    out = svc.verify("s1", spoken_text=CHALLENGE_PHRASE.lower())
    assert out["status"] == "PASSED"


def test_verify_without_start_fails_closed(svc):
    out = svc.verify("ghost")
    assert out["status"] == "FAILED"
    assert "No challenge" in out["note"]


def test_expired_challenge_fails(svc, monkeypatch):
    monkeypatch.setattr(settings, "LIVENESS_EXPIRY_SECONDS", 0)  # expire instantly
    svc.start_challenge("s1")
    out = svc.verify("s1", spoken_text=CHALLENGE_PHRASE)  # even the right phrase
    assert out["status"] == "FAILED"
    assert "expired" in out["note"]


def test_honesty_note_always_present(svc):
    svc.start_challenge("s1")
    out = svc.verify("s1", spoken_text=CHALLENGE_PHRASE)
    assert "cloned voice" in out["note"]  # §9: text match does NOT defeat cloning
