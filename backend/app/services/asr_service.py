"""
ASRService — Hindi/Marathi speech-to-text. (Phase 1 placeholder)

Real implementation arrives in Phase 4:
  Primary:  ai4bharat/indic-conformer-600m-multilingual via transformers
            (trust_remote_code=True) — avoids installing AI4Bharat's NeMo fork.
  Fallback: faster-whisper (pip-installable, CPU-friendly) behind the SAME
            interface, so switching is a one-line config change (§6).

Known limitation to state honestly (§6): code-mixed Hinglish / Marathi-English
speech WILL degrade accuracy. Do not train ASR from scratch.

FUTURE PRODUCT: ASR fine-tuned for Indian languages + code-mixed speech.
"""
import logging

from app.config import settings

log = logging.getLogger(__name__)

# The §3 demo scripts — used as mock transcripts so every demo-mode run
# shows exactly what the primary demo shows (Hindi + Marathi variants).
DEMO_SCRIPTS = {
    "hi": "आपका बैंक अकाउंट बंद होने वाला है। अभी अपना OTP बताइए।",
    "mr": "तुमचे बँक खाते बंद होणार आहे. कृपया आत्ताच OTP सांगा.",
}

# Backwards-compatible alias for the default language.
DEMO_HINDI_SCRIPT = DEMO_SCRIPTS["hi"]


class ASRService:
    has_model = True  # reported in /api/health

    def __init__(self) -> None:
        self.model_loaded = False

    def load_model(self) -> bool:
        """Called ONCE at startup (§19). Phase 4 loads IndicConformer (or the
        faster-whisper fallback) here."""
        self.model_loaded = False
        log.info("ASRService: placeholder — no real model loaded yet (Phase 4)")
        return self.model_loaded

    def transcribe(self, audio, lang: str = "hi") -> dict:
        """Transcribe one audio sample; returns language + transcript (§6).

        `lang` only selects which demo script the mock returns until the real
        model lands in Phase 4 (interface already matches it — no caller
        changes needed then).
        """
        if self.model_loaded:
            raise NotImplementedError("Real ASR inference lands in Phase 4")

        if settings.DEMO_MODE:
            return {
                "language": lang if lang in DEMO_SCRIPTS else "hi",
                "transcript": DEMO_SCRIPTS.get(lang, DEMO_SCRIPTS["hi"]),
                "model": "mock_fallback",
                "note": "DEMO MODE — not real inference (§20)",
            }

        return {"status": "partial", "error": "ASR model unavailable", "fallback_used": True}

    def detect_language(self, audio) -> str:
        """Phase 4: real language id (hi/mr). Prototype assumes the demo language."""
        return "hi"
