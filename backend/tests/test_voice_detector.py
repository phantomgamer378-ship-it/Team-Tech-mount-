"""
Phase 3 tests — VoiceDetector with the real AASIST-L model.

Run from backend/:  python -m pytest -v

Real-model tests auto-download the 426 KB checkpoint on first run and are
skipped (not failed) if the checkpoint can't be made available — so the
suite still passes offline in demo mode (§20 discipline).
"""
import numpy as np
import pytest

from app.config import settings
from app.services.voice_detector import NB_SAMPLES, SPOOF_THRESHOLD, VoiceDetector


@pytest.fixture(scope="module")
def detector():
    """A VoiceDetector with the real checkpoint loaded (module-wide, once)."""
    vd = VoiceDetector()
    if not vd.load_model():
        pytest.skip("AASIST-L checkpoint unavailable (offline?) — real-model tests skipped")
    return vd


# ------------------------------------------------------------- demo mode (§20)

def test_unloaded_detector_returns_demo_mock():
    """No model + DEMO_MODE → clearly-labelled mock, never a crash."""
    vd = VoiceDetector()  # fresh, not loaded
    assert vd.load_model.__doc__  # interface intact
    out = vd.predict(np.zeros(16000, dtype=np.float32))
    assert out["model"] == "mock_fallback"
    assert "DEMO MODE" in out["note"]


# ----------------------------------------------------------- real model (§5)

def test_predict_output_contract(detector):
    out = detector.predict(np.random.randn(NB_SAMPLES).astype(np.float32) * 0.1)

    assert 0.0 <= out["voice_risk"] <= 1.0
    assert 0.0 <= out["confidence"] <= 1.0
    assert 0.0 <= out["p_bonafide"] <= 1.0
    assert isinstance(out["ai_voice"], bool)
    assert out["ai_voice"] == (out["voice_risk"] >= SPOOF_THRESHOLD)
    assert "Hindi/Marathi" in out["model"]  # the §5 disclaimer lives in the label
    assert "aasist" in out["model"].lower()


def test_predict_is_deterministic(detector):
    """Same input twice → identical score (eval mode, no sampling)."""
    x = np.random.RandomState(7).randn(NB_SAMPLES).astype(np.float32) * 0.1
    a = detector.predict(x)
    b = detector.predict(x)
    assert a["voice_risk"] == b["voice_risk"]


def test_short_input_is_zero_padded_not_rejected(detector):
    """1 s of audio works: the detector pads to the official 64600 window
    itself (AudioProcessor's 0.5 s minimum is separate)."""
    out = detector.predict(np.zeros(16000, dtype=np.float32))
    assert "voice_risk" in out


def test_empty_waveform_returns_fallback(detector):
    out = detector.predict(np.zeros(0, dtype=np.float32))
    assert out.get("fallback_used") is True
    assert out["status"] == "partial"


def test_real_speech_like_signal_scores_extreme(detector):
    """
    Sanity only (NOT an accuracy claim, §22): a pure sine is certainly not
    genuine speech, so the pretrained model should give it a high spoof risk.
    This validates score orientation (bonafide=1 column) — if the mapping
    were flipped, this would come out near 0.
    """
    t = np.arange(NB_SAMPLES) / 16000
    sine = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    out = detector.predict(sine)
    assert out["voice_risk"] > 0.5


def test_demo_mode_env_override():
    """DEMO_MODE=false + no model → standard fallback shape (§13/§20)."""
    vd = VoiceDetector()
    original = settings.DEMO_MODE
    try:
        settings.DEMO_MODE = False
        out = vd.predict(np.zeros(16000, dtype=np.float32))
        assert out.get("fallback_used") is True
        assert out["status"] == "partial"
    finally:
        settings.DEMO_MODE = original
