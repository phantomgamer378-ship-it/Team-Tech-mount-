import pytest
from app.services.scam_detector import ScamDetector

@pytest.fixture
def detector():
    return ScamDetector()

def test_empty_transcript(detector):
    result = detector.analyze("")
    assert result["scam_score"] == 0.0
    assert result["category"] == "Unknown"
    assert len(result["indicators"]) == 0

def test_hindi_scam_script(detector):
    script = "आपका बैंक अकाउंट बंद होने वाला है। अभी अपना OTP बताइए।"
    result = detector.analyze(script)
    assert result["scam_score"] > 0.5
    assert "OTP/PIN Request" in result["indicators"]
    assert "Bank/KYC Impersonation" in result["indicators"]

def test_marathi_scam_script(detector):
    script = "तुमचे बँक खाते बंद होणार आहे. कृपया आत्ताच OTP सांगा."
    result = detector.analyze(script)
    assert result["scam_score"] > 0.5
    assert "OTP/PIN Request" in result["indicators"]
    assert "Bank/KYC Impersonation" in result["indicators"]

def test_normal_conversation(detector):
    script = "Hello, how are you? Let's meet at the park tomorrow."
    result = detector.analyze(script)
    assert result["scam_score"] == 0.0
    assert len(result["indicators"]) == 0

def test_police_impersonation(detector):
    script = "I am a police officer and you are under arrest for money laundering."
    result = detector.analyze(script)
    assert result["scam_score"] > 0.3
    assert "Police / Authority Impersonation" in result["indicators"]
