"""
ASRService — Hindi/Marathi speech-to-text (§6). Phase 5: REAL model path.

Two interchangeable backends behind this ONE interface (§MODEL ABSTRACTION,
§6 fallback discipline):

  1. faster_whisper (default, WORKING NOW):
     Systran/faster-whisper (CTranslate2) — pip-installable, CPU int8, not
     gated. Handles Hindi/Marathi reasonably, including some code-mixed
     speech. Model size via settings.WHISPER_MODEL (small default).

  2. indic_conformer (implemented, awaiting HF access):
     ai4bharat/indic-conformer-600m-multilingual via transformers
     (trust_remote_code=True), API verified from the model card:
         transcript = model(wav_16k_mono (1, T), lang_code, "ctc")
     The repo is GATED on Hugging Face: request access on the model page,
     then `huggingface-cli login` and set ASR_BACKEND=indic_conformer.

Load order at startup: configured backend → (on any failure) the other
backend → demo mock (§20). Whichever loads wins and is named in the output.

Honesty requirements (§6):
  * faster-whisper path: `confidence` = model-provided language-ID
    probability (the only confidence Whisper actually emits); IndicConformer
    provides none → None there. Never hard-code a confidence.
  * Code-mixed Hinglish / Marathi-English speech WILL degrade accuracy —
    off-the-shelf models, not fine-tuned. Whisper's own docs note uneven
    per-language performance; never claim validated accuracy (§IMPORTANT
    SCIENTIFIC RULE). Never claim Whisper detects fake voices — the
    anti-spoof decision belongs to the dedicated VoiceDetector (§WHISPER ROLE).

FUTURE PRODUCT: ASR fine-tuned for Indian languages + code-mixed speech;
tracked via WER/CER per language (§FUTURE ASR TRAINING).
"""
import logging
import re

import numpy as np

from app.config import settings

log = logging.getLogger(__name__)

SUPPORTED_LANGS = ("hi", "mr")   # prototype targets (both backends support more)
MAX_ASR_SECONDS = 120            # CPU prototype guard for absurdly long uploads


class ASRService:
    has_model = True  # reported in /api/health

    def __init__(self) -> None:
        self.model = None
        self.backend: str | None = None   # "faster_whisper" | "indic_conformer" | None
        self.model_loaded = False

    # ------------------------------------------------------------------ setup

    def load_model(self) -> bool:
        """Called ONCE at startup (§19). Tries the configured backend first,
        then the other one, then gives up into demo fallback (§20)."""
        if self.model_loaded:
            return True

        order = [settings.ASR_BACKEND, "indic_conformer" if settings.ASR_BACKEND == "faster_whisper" else "faster_whisper"]
        for backend in order:
            loader = self._load_faster_whisper if backend == "faster_whisper" else self._load_indic_conformer
            if loader():
                return True
        log.warning("ASRService: no backend loaded — demo fallback stays (§20)")
        return False

    def _load_faster_whisper(self) -> bool:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            log.warning("ASRService: faster-whisper not installed (%s)", exc)
            return False
        try:
            log.info("ASRService: loading faster-whisper '%s' on CPU int8 "
                     "(first run downloads the model)...", settings.WHISPER_MODEL)
            model = WhisperModel(
                settings.WHISPER_MODEL, device="cpu", compute_type="int8"
            )
            self.model, self.backend, self.model_loaded = model, "faster_whisper", True
            log.info("ASRService: faster-whisper '%s' ready", settings.WHISPER_MODEL)
            return True
        except Exception as exc:
            log.warning("ASRService: faster-whisper load failed (%s)", exc)
            return False

    def _load_indic_conformer(self) -> bool:
        try:
            from transformers import AutoModel
        except ImportError as exc:
            log.warning("ASRService: transformers not installed (%s)", exc)
            return False
        try:
            log.info("ASRService: loading %s ...", settings.ASR_MODEL)
            model = AutoModel.from_pretrained(settings.ASR_MODEL, trust_remote_code=True)
            model.eval()
            self.model, self.backend, self.model_loaded = model, "indic_conformer", True
            log.info("ASRService: IndicConformer ready")
            return True
        except Exception as exc:
            log.warning(
                "ASRService: IndicConformer load failed (%s) — NOTE: the HF repo "
                "is gated; request access on the model page and run "
                "`huggingface-cli login` before enabling this backend.", exc,
            )
            return False

    # --------------------------------------------------------------- inference

    def transcribe(self, audio, lang: str = "hi", source_hint: str = "") -> dict:
        """
        Transcribe one 16 kHz mono waveform; returns the frozen-contract ASR
        block. `source_hint` only steers the demo mock (see app/demo). This
        method never raises (§20).
        """
        # Validate input BEFORE any backend/mock dispatch: bad input must get
        # the fallback shape, not a demo mock that pretends the input was fine.
        try:
            waveform = self._prepare(audio)
        except ValueError as exc:
            return {"status": "partial", "error": str(exc), "fallback_used": True}

        if self.model_loaded:
            try:
                if self.backend == "faster_whisper":
                    return self._transcribe_faster_whisper(waveform, lang)
                return self._transcribe_indic_conformer(waveform, lang)
            except Exception as exc:
                log.warning("ASRService: inference failed (%s)", exc)
                if settings.DEMO_MODE:
                    return self._mock(lang, source_hint)
                return {"status": "partial", "error": f"ASR failed: {exc}", "fallback_used": True}

        if settings.DEMO_MODE:
            return self._mock(lang, source_hint)

        return {"status": "partial", "error": "ASR model unavailable", "fallback_used": True}

    # ------------------------------------------------------------ backends

    def _prepare(self, audio) -> np.ndarray:
        waveform = np.asarray(audio, dtype=np.float32).reshape(-1)
        if waveform.size == 0:
            raise ValueError("Empty waveform")
        if waveform.shape[0] > MAX_ASR_SECONDS * 16000:
            log.warning("ASRService: clipping to first %s s (CPU prototype guard)", MAX_ASR_SECONDS)
            waveform = waveform[: MAX_ASR_SECONDS * 16000]
        return waveform

    def _lang_or_default(self, lang: str) -> str:
        if lang not in SUPPORTED_LANGS:
            log.warning("ASRService: lang '%s' not in prototype targets %s — using 'hi'",
                        lang, SUPPORTED_LANGS)
            return "hi"
        return lang

    def _transcribe_faster_whisper(self, waveform: np.ndarray, lang: str) -> dict:
        lang = self._lang_or_default(lang)

        # faster-whisper accepts float32 16 kHz mono numpy directly.
        segments_iter, info = self.model.transcribe(
            waveform, language=lang, beam_size=5,
            vad_filter=False,  # short demo clips; VAD would drop trailing speech
        )
        segments, texts = [], []
        for seg in segments_iter:  # generator — consumes real inference
            segments.append({"start": round(seg.start, 2), "end": round(seg.end, 2),
                             "text": seg.text.strip()})
            texts.append(seg.text.strip())
        transcript = re.sub(r"\s+", " ", " ".join(texts)).strip()

        return {
            "language": lang,
            "transcript": transcript,
            "segments": segments,  # real model-provided timing (faster-whisper)
            # The ONLY confidence the model actually provides: language-ID
            # probability. Documented semantics — not transcription confidence.
            "confidence": round(float(info.language_probability), 4),
            "model": f"faster-whisper-{settings.WHISPER_MODEL} (pretrained, Systran/CTranslate2)",
            "note": (
                "Off-the-shelf Whisper-class ASR; uneven per-language performance, "
                "code-mixed speech degrades — not fine-tuned (§6). Whisper does "
                "NOT judge voice authenticity. PROTOTYPE."
            ),
        }

    def _transcribe_indic_conformer(self, waveform: np.ndarray, lang: str) -> dict:
        import torch

        lang = self._lang_or_default(lang)

        wav = torch.from_numpy(waveform).unsqueeze(0)  # (1, T) float32 @ 16 kHz
        with torch.no_grad():
            transcript = self.model(wav, lang, "ctc")

        if isinstance(transcript, (list, tuple)):
            transcript = transcript[0]
        transcript = re.sub(r"\s+", " ", str(transcript)).strip()

        return {
            "language": lang,
            "transcript": transcript,
            "segments": [],       # honest: CTC gives one string, no timing (§6)
            "confidence": None,   # honest: model provides none — never hard-code
            "model": "indic-conformer-600m-multilingual (ctc, pretrained)",
            "note": (
                "Off-the-shelf pretrained IndicConformer; code-mixed speech "
                "degrades accuracy — not fine-tuned (§6). PROTOTYPE."
            ),
        }

    def _mock(self, lang: str = "hi", source_hint: str = "") -> dict:
        """§20/§DEMO — delegate to the shared demo mock (one mock, one truth)."""
        from app.demo import DemoASRService

        return DemoASRService().transcribe(lang=lang, source_hint=source_hint)

    def detect_language(self, audio, source_hint: str = "") -> str:
        """Prototype: explicit lang param wins; both backends perform LID
        internally but the pipeline passes the target language explicitly."""
        return "hi"
