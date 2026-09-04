"""
Generate synthetic test WAVs for development (no internet, no TTS needed).

Usage (from the repo root, with the venv active):
    source backend/.venv/bin/activate
    python scripts/gen_test_audio.py

Creates in demo_data/:
    test_tone_16k.wav        1 kHz sine, 16 kHz mono, 2 s  (already target format)
    test_tone_44k_stereo.wav 1 kHz sine, 44.1 kHz stereo, 2 s (exercises resample+mono)
    test_babble_16k.wav      speech-like babble (sines + noise envelope), 16 kHz mono, 4 s
    test_too_short.wav       0.2 s tone — the pipeline MUST reject this (§20 check)

NOTE (§21): these are synthetic placeholders, NOT real Hindi/Marathi scam
recordings and NOT TTS output. Team-recorded + TTS demo audio is a later phase.
"""
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent / "demo_data"


def write_wav(name: str, sr: int, data: np.ndarray) -> Path:
    path = OUT_DIR / name
    data16 = np.clip(data * 32767, -32768, 32767).astype(np.int16)
    sf.write(path, data16, sr, subtype="PCM_16")
    print(f"  wrote {path.name:24s} {sr/1000:>5.1f} kHz  {len(data)/sr:>4.1f} s")
    return path


def sine(seconds: float, sr: int, freq: float = 1000.0, gain: float = 0.5) -> np.ndarray:
    t = np.arange(int(sr * seconds)) / sr
    return (gain * np.sin(2 * np.pi * freq * t)).astype(np.float64)


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    print(f"Generating synthetic test audio in {OUT_DIR}/")

    write_wav("test_tone_16k.wav", 16000, sine(2.0, 16000))
    write_wav("test_tone_44k_stereo.wav", 44100, np.stack([sine(2.0, 44100), sine(2.0, 44100, gain=0.25)], axis=1))

    # Speech-like babble: a few 'formant' sines under a slow noise envelope.
    sr = 16000
    t = np.arange(int(sr * 4.0)) / sr
    envelope = 0.5 * (1 + np.sign(np.sin(2 * np.pi * 3.0 * t))) * (0.6 + 0.4 * np.random.rand(len(t)))
    babble = 0.4 * envelope * (
        0.5 * np.sin(2 * np.pi * 220 * t)
        + 0.3 * np.sin(2 * np.pi * 700 * t)
        + 0.2 * np.sin(2 * np.pi * 1200 * t)
        + 0.05 * np.random.randn(len(t))
    )
    write_wav("test_babble_16k.wav", sr, babble)

    write_wav("test_too_short.wav", sr, sine(0.2, sr))

    print("Done. Try: python scripts/check_audio.py demo_data/test_tone_44k_stereo.wav")


if __name__ == "__main__":
    main()
