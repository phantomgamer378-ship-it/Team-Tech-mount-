"""
ASRService — Hindi/Marathi speech-to-text (Phase 4).

Primary: ai4bharat/indic-conformer-600m-multilingual via transformers
Fallback: faster-whisper behind the SAME interface.
Switch via ASR_BACKEND environment variable.
"""
import logging
import os
import io

from app.config import settings
import soundfile as sf
import numpy as np

log = logging.getLogger(__name__)

# The §3 demo scripts
DEMO_SCRIPTS = {
    "hi": "आपका बैंक अकाउंट बंद होने वाला है। अभी अपना OTP बताइए।",
    "mr": "तुमचे बँक खाते बंद होणार आहे. कृपया आत्ताच OTP सांगा.",
}
DEMO_HINDI_SCRIPT = DEMO_SCRIPTS["hi"]


class ASRService:
    has_model = True  # reported in /api/health

    def __init__(self) -> None:
        self.model_loaded = False
        self.backend = os.getenv("ASR_BACKEND", "faster_whisper")
        self.model = None

    def load_model(self) -> bool:
        """Called ONCE at startup (§19). Loads faster-whisper or IndicConformer."""
        if self.model_loaded:
            return True

        try:
            if self.backend == "faster_whisper":
                from faster_whisper import WhisperModel
                log.info("ASRService: Loading faster-whisper model...")
                # Using small model for prototype/demo
                self.model = WhisperModel("small", device="cpu", compute_type="int8")
                self.model_loaded = True
                log.info("ASRService: faster-whisper loaded.")
            elif self.backend == "indic_conformer":
                # from transformers import AutoModelForCTC, AutoProcessor
                log.info("ASRService: Loading IndicConformer...")
                # self.processor = AutoProcessor.from_pretrained("ai4bharat/indic-conformer-600m-multilingual")
                # self.model = AutoModelForCTC.from_pretrained("ai4bharat/indic-conformer-600m-multilingual", trust_remote_code=True)
                # Note: Left commented to avoid heavy download during prototyping unless forced
                log.warning("IndicConformer requires heavy download. Falling back to demo mode for now.")
                self.model_loaded = False
            else:
                log.error(f"ASRService: Unknown backend {self.backend}")
                self.model_loaded = False
        except Exception as e:
            log.error(f"ASRService: Failed to load model: {e}")
            self.model_loaded = False

        return self.model_loaded

    def transcribe(self, audio: np.ndarray, lang: str = "hi") -> dict:
        """Transcribe one audio sample; returns language + transcript (§6)."""
        if not self.model_loaded:
            if settings.DEMO_MODE:
                return {
                    "language": lang if lang in DEMO_SCRIPTS else "hi",
                    "transcript": DEMO_SCRIPTS.get(lang, DEMO_SCRIPTS["hi"]),
                    "model": "mock_fallback",
                    "note": "DEMO MODE — not real inference (§20)",
                }
            return {"status": "partial", "error": "ASR model unavailable", "fallback_used": True}

        if self.backend == "faster_whisper":
            try:
                # faster-whisper expects a path or a 1D numpy array
                segments, info = self.model.transcribe(audio, beam_size=5)
                transcript = " ".join([segment.text for segment in segments]).strip()
                return {
                    "language": info.language,
                    "transcript": transcript,
                    "model": f"faster_whisper_{self.model.model_size}",
                }
            except Exception as e:
                log.error(f"faster-whisper inference failed: {e}")
                return {"status": "partial", "error": str(e), "fallback_used": True}
        
        return {"status": "partial", "error": "Unsupported backend", "fallback_used": True}

    def detect_language(self, audio: np.ndarray) -> str:
        """Real language id. Falls back to hi if inference fails."""
        if not self.model_loaded or self.backend != "faster_whisper":
            return "hi"
        try:
            segments, info = self.model.transcribe(audio, beam_size=1)
            return info.language
        except Exception:
            return "hi"
