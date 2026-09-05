"""
Pre-download the ASR models so the demo never depends on venue Wi-Fi (§24).

Usage (from repo root, venv active):
    python scripts/download_asr_model.py

Downloads/verifies whichever backend is configured:
  * faster_whisper   → Systran/faster-whisper-<WHISPER_MODEL> (~465 MB 'small',
                       not gated — the default working backend)
  * indic_conformer  → ai4bharat/indic-conformer-600m-multilingual (~2.4 GB)
                       GATED on Hugging Face: you must first request access at
                       https://huggingface.co/ai4bharat/indic-conformer-600m-multilingual
                       and authenticate (`huggingface-cli login` or HF_TOKEN env).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))  # noqa: E402

from app.config import settings  # noqa: E402


def main() -> int:
    backend = settings.ASR_BACKEND
    print(f"ASR backend: {backend}")

    if backend == "faster_whisper":
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            print("faster-whisper not installed — run: pip install -r requirements.txt")
            return 1
        print(f"Loading faster-whisper '{settings.WHISPER_MODEL}' "
              "(first run downloads it)...")
        try:
            model = WhisperModel(settings.WHISPER_MODEL, device="cpu", compute_type="int8")
            del model
        except Exception as exc:
            print(f"FAILED: {exc}")
            return 1
        print("OK — faster-whisper cached for offline startup")
        return 0

    if backend == "indic_conformer":
        try:
            from transformers import AutoModel
        except ImportError:
            print("transformers not installed — run: pip install -r requirements.txt")
            return 1
        print(f"Loading {settings.ASR_MODEL} (~2.4 GB, GATED — needs HF access + token)...")
        try:
            model = AutoModel.from_pretrained(settings.ASR_MODEL, trust_remote_code=True)
            del model
        except Exception as exc:
            print(f"FAILED: {exc}")
            print("The repo is gated: request access on the model page, then run "
                  "`huggingface-cli login` and retry. faster-whisper keeps working "
                  "in the meantime (same interface, ASR_BACKEND=faster_whisper).")
            return 1
        print("OK — IndicConformer cached for offline startup")
        return 0

    print(f"Unknown ASR_BACKEND: {backend}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
