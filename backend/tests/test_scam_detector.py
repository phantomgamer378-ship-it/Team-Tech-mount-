"""
Phase 7 tests — the scam rule engine (services/scam_detector.py).

The key regression set: the ACTUAL faster-whisper transcripts from our TTS
samples (phonetic spellings like अटीपी/बन्द) must match — that's the real
pipeline, not idealized text.

Run from backend/:  python -m pytest -v
"""
import pytest

from app.services.scam_detector import ScamDetector


@pytest.fixture
def detector():
    return ScamDetector()


# --------------------------------------------------- master prompt examples

def test_english_bank_scam(detector):
    """The §SCAM INTENT DETECTION example, verbatim."""
    out = detector.analyze(
        "Sir I am calling from your bank. Your account will be blocked today. "
        "Please share the OTP immediately."
    )
    assert out["model"] == "rule_engine" and out["note"] is None
    assert out["category"] == "Bank/KYC Fraud"
    for expected in ("Bank impersonation", "Account-blocking threat",
                     "Urgency", "OTP request"):
        assert expected in out["indicators"], out["indicators"]
    assert out["risk"] >= 0.7
    assert any("[scam_rule]" in e for e in out["evidence"])


def test_hindi_bank_scan_script(detector):
    out = detector.analyze("आपका बैंक अकाउंट बंद होने वाला है। अभी अपना OTP बताइए।")
    assert out["category"] == "Bank/KYC Fraud"
    assert "Bank impersonation" in out["indicators"]
    assert "OTP request" in out["indicators"]
    assert out["risk"] >= 0.7


def test_marathi_bank_script(detector):
    out = detector.analyze("तुमचे बँक खाते बंद होणार आहे. कृपया आत्ताच OTP सांगा.")
    assert out["category"] == "Bank/KYC Fraud"
    assert "OTP request" in out["indicators"]
    assert out["risk"] >= 0.7


def test_marathi_family_emergency(detector):
    """The master prompt's Marathi attack example (§DEMO EXAMPLE)."""
    out = detector.analyze(
        "आई, मी राहुल बोलतोय. माझा accident झाला आहे. मला लगेच पन्नास हजार रुपये पाठव."
    )
    assert out["category"] == "Family Emergency Scam"
    assert "Family-member impersonation" in out["indicators"]
    assert "Emergency claim" in out["indicators"]
    assert "Financial transfer request" in out["indicators"]
    assert out["risk"] >= 0.7


# ------------------------------------------- REAL whisper transcripts (variants)

def test_real_whisper_hindi_variants_normalized(detector):
    """Actual faster-whisper-small output for our TTS Hindi scam clip —
    phonetic spellings must be folded back before matching."""
    out = detector.analyze(
        "अपका बैंक अकाून्त बन्द होने वाला है अभी अपना अटीपी बता ये"
    )
    assert "Bank impersonation" in out["indicators"]
    assert "OTP request" in out["indicators"]          # अटीपी → ओटीपी
    assert "Account-blocking threat" in out["indicators"]  # बन्द → बंद
    assert out["risk"] >= 0.7


def test_real_whisper_marathi_variants_normalized(detector):
    """Actual faster-whisper-small output for the TTS Marathi scam clip."""
    out = detector.analyze(
        "तुम्चे बैंक खाते बन्द होना रहे, क्रुपया अथा चो ती पी सांगा."
    )
    assert "Bank impersonation" in out["indicators"]
    assert "OTP request" in out["indicators"]          # ती पी → ओटीपी
    assert out["risk"] >= 0.5


# ------------------------------------------------------------- negative cases

def test_normal_hindi_conversation_scores_zero(detector):
    out = detector.analyze("नमस्ते, सब ठीक है? कल मिलते हैं, धन्यवाद।")
    assert out["risk"] == 0.0
    assert out["indicators"] == []
    assert out["category"] == "Normal conversation"


def test_normal_english_conversation_scores_zero(detector):
    out = detector.analyze("Hey, how was your day? See you tomorrow at the office.")
    assert out["risk"] == 0.0
    assert out["indicators"] == []


def test_empty_transcript_is_a_clean_no_signal(detector):
    out = detector.analyze("")
    assert out["risk"] == 0.0 and out["category"] == "Normal conversation"
    out = detector.analyze("   ")
    assert out["risk"] == 0.0


def test_generic_suspicious_when_no_category_rule(detector):
    """A single urgency mention with nothing else → generic, low score."""
    out = detector.analyze("call me today please")
    assert out["category"] == "Suspicious conversation"
    assert out["risk"] <= 0.2


def test_deterministic(detector):
    text = "bank account blocked, share OTP immediately"
    assert detector.analyze(text) == detector.analyze(text)
