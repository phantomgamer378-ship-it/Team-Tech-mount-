"""
Pre-download the AASIST-L voice model checkpoint (§24: download the night
before, cache locally — don't depend on venue Wi-Fi).

Usage (from repo root, venv active):
    python scripts/download_voice_model.py

Idempotent: skips if the checkpoint already exists and looks valid.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))  # noqa: E402

from app.config import settings  # noqa: E402
from app.services.voice_detector import VoiceDetector  # noqa: E402


def main() -> int:
    dest = Path(settings.VOICE_MODEL_PATH)
    if dest.is_file() and dest.stat().st_size > 10_000:
        print(f"Already present: {dest} ({dest.stat().st_size} bytes) — nothing to do")
        return 0

    ok = VoiceDetector()._download_weights(dest)
    if ok:
        print(f"Saved: {dest} ({dest.stat().st_size} bytes)")
        return 0
    print("Download failed from all URLs — check internet or set VOICE_MODEL_URL in .env")
    return 1


if __name__ == "__main__":
    sys.exit(main())
