"""
Phase 2 tests — the §14 audio pipeline.

Run from backend/:  python -m pytest -v

All test WAVs are generated inline (numpy + soundfile), so no real audio
files are needed. §21 (team-recorded + TTS demo audio) is a later phase.
"""
import numpy as np
import pytest
import soundfile as sf

from app.services.audio_processor import TARGET_SR, AudioProcessor


def make_wav(path, sr=44100, seconds=2.0, channels=1, freq=440.0, gain=0.5):
    """Write a synthetic sine-wave WAV; returns the file path."""
    t = np.arange(int(sr * seconds)) / sr
    sine = (gain * np.sin(2 * np.pi * freq * t)).astype(np.float64)
    if channels == 1:
        data = sine
    else:  # slightly different per channel so mono-averaging is observable
        data = np.stack([sine, sine * 0.5], axis=1)
    data16 = np.clip(data * 32767, -32768, 32767).astype(np.int16)
    sf.write(path, data16, sr, subtype="PCM_16")
    return path


@pytest.fixture
def processor():
    return AudioProcessor()


# --------------------------------------------------------------- happy path

def test_resamples_44k_stereo_to_16k_mono(processor, tmp_path):
    wav = make_wav(tmp_path / "in.wav", sr=44100, seconds=2.0, channels=2)

    result = processor.preprocess(wav)

    assert result["ok"] is True
    assert result["status"] == "ok"
    assert result["sample_rate"] == TARGET_SR == 16000
    assert result["source_sr"] == 44100
    assert result["channels_in"] == 2
    # ~2s of audio at 16 kHz → ~32000 samples (resampling tolerance)
    assert result["n_samples"] == pytest.approx(32000, abs=350)
    assert result["duration_s"] == pytest.approx(2.0, abs=0.05)
    assert result["waveform"].ndim == 1  # mono


def test_16k_mono_passthrough_keeps_length(processor, tmp_path):
    wav = make_wav(tmp_path / "in.wav", sr=16000, seconds=1.0, channels=1)

    result = processor.preprocess(wav)

    assert result["ok"] is True
    assert result["source_sr"] == 16000
    assert result["n_samples"] == 16000


def test_output_is_peak_normalized(processor, tmp_path):
    # quiet input (gain 0.25) should be scaled up to full scale
    wav = make_wav(tmp_path / "quiet.wav", sr=16000, seconds=1.0, gain=0.25)

    result = processor.preprocess(wav)

    assert result["ok"] is True
    peak = float(np.max(np.abs(result["waveform"])))
    assert peak == pytest.approx(1.0, abs=0.01)


# ------------------------------------------------- §20 failure modes (no crash)

def test_missing_file_returns_fallback(processor, tmp_path):
    result = processor.preprocess(tmp_path / "nope.wav")

    assert result["ok"] is False
    assert result["status"] == "partial"
    assert result["fallback_used"] is True
    assert "not found" in result["error"]


def test_too_short_audio_returns_fallback(processor, tmp_path):
    wav = make_wav(tmp_path / "short.wav", sr=16000, seconds=0.2)

    result = processor.preprocess(wav)

    assert result["fallback_used"] is True
    assert "too short" in result["error"]


def test_corrupt_file_returns_fallback(processor, tmp_path):
    bogus = tmp_path / "corrupt.wav"
    bogus.write_bytes(b"this is definitely not audio data")

    result = processor.preprocess(bogus)

    assert result["fallback_used"] is True
    assert result["status"] == "partial"


def test_unsupported_extension_returns_fallback(processor, tmp_path):
    m4a = tmp_path / "voice.m4a"
    m4a.write_bytes(b"\x00" * 100)

    result = processor.preprocess(m4a)

    assert result["fallback_used"] is True
    assert "Unsupported audio type" in result["error"]


def test_oversized_file_returns_fallback(processor, tmp_path, monkeypatch):
    from app.services import audio_processor as ap

    monkeypatch.setattr(ap.settings, "MAX_UPLOAD_MB", 0)  # 0 MB → everything rejected
    wav = make_wav(tmp_path / "big.wav", sr=16000, seconds=1.0)

    result = processor.preprocess(wav)

    assert result["fallback_used"] is True
    assert "too large" in result["error"]


# ------------------------------------------------------------- chunk utility

def test_chunk_splits_into_1s_windows(processor, tmp_path):
    wav = make_wav(tmp_path / "in.wav", sr=16000, seconds=3.0)
    result = processor.preprocess(wav)

    chunks = processor.chunk(result["waveform"], chunk_seconds=1.0)

    assert len(chunks) == 3
    assert all(len(c) == 16000 for c in chunks)


def test_chunk_keeps_short_remainder(processor, tmp_path):
    wav = make_wav(tmp_path / "in.wav", sr=16000, seconds=3.5)
    result = processor.preprocess(wav)

    chunks = processor.chunk(result["waveform"], chunk_seconds=1.0)

    assert len(chunks) == 4
    assert len(chunks[-1]) == 8000  # the half-second remainder is kept


def test_mono_averaging_of_stereo(processor):
    stereo = np.array([[1.0, 0.5], [0.2, 0.2]], dtype=np.float32)

    mono = processor.to_mono(stereo)

    assert mono.shape == (2,)
    assert mono[0] == pytest.approx(0.75)
