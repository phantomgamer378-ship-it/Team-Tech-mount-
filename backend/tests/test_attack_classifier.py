"""
Phase 7 tests — attack_types_from_indicators() (§ATTACK-TYPE CLASSIFICATION).

Pure lookup: deterministic, multi-label, no model. The §8 master-prompt rule:
"This is NOT a separate ML model — do not build one."
"""
from app.services.attack_classifier import attack_types_from_indicators


def test_otp_plus_bank_is_bank_fraud_and_otp_theft():
    types = attack_types_from_indicators(
        ["Bank impersonation", "OTP request", "Urgency"], voice_spoof_risk=0.93
    )
    assert "Bank Fraud" in types
    assert "OTP Theft" in types
    assert "AI Voice Impersonation" in types      # voice evidence included
    assert types[-1] == "Social Engineering"      # always last, only when specific hits


def test_family_emergency_scenario():
    types = attack_types_from_indicators(
        ["Family-member impersonation", "Emergency claim",
         "Urgency", "Financial transfer request"],
        voice_spoof_risk=0.02,  # real human voice pretending to be a relative
    )
    assert "Family Emergency Scam" in types
    assert "Financial Fraud" in types
    assert "AI Voice Impersonation" not in types   # spoof below threshold
    assert "Social Engineering" in types


def test_police_impersonation():
    types = attack_types_from_indicators(
        ["Police impersonation", "Secrecy request", "Urgency"]
    )
    assert "Authority Impersonation" in types
    assert "Coercion & Secrecy" in types


def test_no_indicators_means_no_labels():
    assert attack_types_from_indicators([]) == []
    assert attack_types_from_indicators(None) == []


def test_voice_evidence_alone_triggers_ai_voice_label():
    """High spoof risk with NO scam indicators is still an attack signal."""
    types = attack_types_from_indicators([], voice_spoof_risk=0.91)
    assert types == ["AI Voice Impersonation"]


def test_pure_function_is_deterministic():
    a = attack_types_from_indicators(["Bank impersonation", "OTP request"])
    b = attack_types_from_indicators(["Bank impersonation", "OTP request"])
    assert a == b
