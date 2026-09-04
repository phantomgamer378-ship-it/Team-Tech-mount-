"""
Run the §14 AudioProcessor pipeline on one audio file and print a summary.

Usage (from the repo root, with the venv active):
    python scripts/check_audio.py demo_data/test_tone_44k_stereo.wav
    python scripts/check_audio.py demo_data/test_too_short.wav   # shows the fallback path
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))  # noqa: E402

from app.services.audio_processor import TARGET_SR, AudioProcessor  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: python {Path(__file__).name} <audio-file>")
        sys.exit(1)

    result = AudioProcessor().preprocess(sys.argv[1])

    if not result.get("ok"):
        print(json.dumps(result, indent=2))
        sys.exit(0)  # a graceful fallback is correct behaviour, not an error

    waveform = result.pop("waveform")
    print(json.dumps(result, indent=2))
    print(f"\n  peak level : {float(abs(waveform).max()):.3f}  (≈1.0 after normalization)")
    print(f"  1 s chunks : {len(AudioProcessor().chunk(waveform))} (for Phase 9 streaming sim)")

    if result["sample_rate"] != TARGET_SR:
        print(f"  WARNING: sample rate {result['sample_rate']} != target {TARGET_SR}")


if __name__ == "__main__":
    main()
