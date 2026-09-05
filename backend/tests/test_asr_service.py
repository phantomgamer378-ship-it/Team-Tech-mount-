"""
Phase 5 tests — ASRService with real faster-whisper (+ IndicConformer-ready).

Run from backend/:  python -m pytest -v

Real-model tests skip (not fail) if the model can't be made available —
suite still passes offline (§20 discipline). Pre-download with
scripts/download_asr_model.py.
"""
import numpy as np
import pytest

from app.config import settings
from app.models.schemas import ASRInfo
from app.services.asr_service import ASRService


@pytest.fixture(scope="module")
def asr():
    """ASRService with a real backend loaded (module-wide, once)."""
    svc = ASRService()
    if not svc.load_model():
        pytest.skip("No ASR backend available (offline?) — real-model tests skipped")
    return svc


# ------------------------------------------------------------- demo mode (§20)

def test_unloaded_service_returns_demo_mock():
    """No model + DEMO_MODE → contract-shaped demo mock, never a crash."""
    svc = ASRService()  # fresh, not loaded
    out = svc.transcribe(np.zeros(16000, dtype=np.float32))

    block = ASRInfo(**out)  # raises if the shape deviates from the contract
    assert out["model"] == "mock_fallback"
    assert "DEMO MODE" in out["note"]
    assert out["confidence"] is None          # never hard-code a confidence
    assert out["transcript"]                  # canned §3 script present


def test_demo_mock_hint_and_language():
    svc = ASRService()
    hi_scam = svc.transcribe(None, lang="hi", source_hint="hindi_scam.wav")
    mr_scam = svc.transcribe(None, lang="mr", source_hint="marathi_scam.wav")
    normal = svc.transcribe(None, lang="hi", source_hint="normal_call.wav")
    assert hi_scam["language"] == "hi" and mr_scam["language"] == "mr"
    assert normal["transcript"] != hi_scam["transcript"]  # normal hint → control script


# ----------------------------------------------------------- real model (§6)

def test_real_backend_loaded(asr):
    assert asr.model_loaded is True
    assert asr.backend in ("faster_whisper", "indic_conformer")


def test_real_transcription_contract(asr, tmp_path):
    """End-to-end on the TTS Hindi scam sample (if present)."""
    sample = tmp_path  # placeholder to keep fixture signature simple
    from pathlib import Path

    wav_path = Path(__file__).resolve().parent.parent.parent / "demo_data" / "tts_hindi_scam.mp3"
    if not wav_path.exists():
        pytest.skip("demo_data/tts_hindi_scam.mp3 missing (run scripts/generate_tts_samples.py)")

    from app.services.audio_processor import AudioProcessor
    pre = AudioProcessor().preprocess(wav_path)
    assert pre["ok"], pre.get("error")  # mp3 support sanity

    out = asr.transcribe(pre["waveform"], lang="hi")

    block = ASRInfo(**out)  # contract shape
    assert out["model"] != "mock_fallback"
    assert out["language"] == "hi"
    assert len(out["transcript"]) >= 10       # real speech → substantial text
    if asr.backend == "faster_whisper":
        assert out["confidence"] is not None   # model-provided LID probability
        assert out["segments"], "faster-whisper provides real segment timing"
    else:
        assert out["confidence"] is None       # IndicConformer provides none


def test_real_transcription_is_deterministic(asr):
    from pathlib import Path

    wav_path = Path(__file__).resolve().parent.parent.parent / "demo_data" / "tts_hindi_scam.mp3"
    if not wav_path.exists():
        pytest.skip("demo_data/tts_hindi_scam.mp3 missing")

    from app.services.audio_processor import AudioProcessor
    waveform = AudioProcessor().preprocess(wav_path)["waveform"]
    a = asr.transcribe(waveform, lang="hi")
    b = asr.transcribe(waveform, lang="hi")
    assert a["transcript"] == b["transcript"]


def test_real_marathi_language_param(asr):
    from pathlib import Path

    wav_path = Path(__file__).resolve().parent.parent.parent / "demo_data" / "tts_marathi_scam.mp3"
    if not wav_path.exists():
        pytest.skip("demo_data/tts_marathi_scam.mp3 missing")

    from app.services.audio_processor import AudioProcessor
    waveform = AudioProcessor().preprocess(wav_path)["waveform"]
    out = asr.transcribe(waveform, lang="mr")
    assert out["language"] == "mr"
    assert out["transcript"]


def test_empty_waveform_returns_fallback(asr):
    out = asr.transcribe(np.zeros(0, dtype=np.float32))
    assert out.get("fallback_used") is True
    assert out["status"] == "partial"


def test_unsupported_language_falls_back_to_hi(asr):
    out = asr.transcribe(np.zeros(16000, dtype=np.float32), lang="fr")
    assert out["language"] == "hi"  # prototype targets hi/mr only (§6)
