import pytest
from app.risk.risk_engine import RiskEngine

@pytest.fixture
def engine():
    return RiskEngine()

def test_risk_fuse_all_high(engine):
    result = engine.fuse(voice_risk=1.0, scam_risk=1.0, context_risk=1.0)
    assert result["risk_score"] == 100
    assert result["risk_level"] == "HIGH"

def test_risk_fuse_all_low(engine):
    result = engine.fuse(voice_risk=0.0, scam_risk=0.0, context_risk=0.0)
    assert result["risk_score"] == 0
    assert result["risk_level"] == "LOW"

def test_risk_fuse_boundaries(engine):
    # Score 29 -> LOW
    # voice=0.725 (0.4*0.725 = 0.29 -> 29)
    result = engine.fuse(voice_risk=0.725, scam_risk=0.0, context_risk=0.0)
    assert result["risk_score"] == 29
    assert result["risk_level"] == "LOW"
    
    # Score 30 -> MEDIUM
    result = engine.fuse(voice_risk=0.75, scam_risk=0.0, context_risk=0.0)
    assert result["risk_score"] == 30
    assert result["risk_level"] == "MEDIUM"

    # Score 69 -> MEDIUM
    result = engine.fuse(voice_risk=1.0, scam_risk=0.725, context_risk=0.0) # 0.4 + 0.29 = 0.69
    assert result["risk_score"] == 69
    assert result["risk_level"] == "MEDIUM"

    # Score 70 -> HIGH
    result = engine.fuse(voice_risk=1.0, scam_risk=0.75, context_risk=0.0) # 0.4 + 0.3 = 0.70
    assert result["risk_score"] == 70
    assert result["risk_level"] == "HIGH"

def test_risk_fuse_clamping(engine):
    # Inputs above 1.0 should be clamped to 1.0
    result = engine.fuse(voice_risk=1.5, scam_risk=2.0, context_risk=-1.0)
    # voice=1.0, scam=1.0, context=0.0 => 0.4 + 0.4 + 0 = 0.8 => 80
    assert result["risk_score"] == 80
    assert result["risk_level"] == "HIGH"

def test_calibrate_hook(engine, caplog):
    # Test that calibrate hook runs without errors
    engine.calibrate(classifier_path="/dummy/path")
    assert "calibrate() hook called" in caplog.text
