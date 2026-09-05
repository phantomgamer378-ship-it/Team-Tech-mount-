"""
VoiceDetector — AI voice / deepfake detection (§5). Phase 3: REAL model path.

Model: AASIST-L anti-spoofing (light graph-attention variant), pretrained on
ASVspoof2019 LA. Architecture: app/ml/aasist.py (official, MIT). Checkpoint:
SpeechAntiSpoofingBenchmarks/AASIST-L on Hugging Face — mirrors the official
clovaai checkpoint; auto-downloaded (426 KB) on first startup if missing.

How the score works (official convention, verified from the reference code):
  * model output = 2 logits [spoof, bonafide]; bonafide label is 1
  * eval score = logits softmax -> P(bonafide); higher = more genuine
  * we report spoof_risk = 1 - P(bonafide)  (0 = genuine … 1 = synthetic)
  * status = SUSPICIOUS if spoof_risk >= SPOOF_THRESHOLD else GENUINE
    (0.5 — UNCALIBRATED prototype cut)

Honesty requirements (§5) — repeat in UI and README, never hide:
  * ~1% EER on ASVspoof2019-LA (its own benchmark), 12–17% EER on
    ASVspoof2021, 40%+ on "in the wild" audio (published figures for the
    family — cite, don't claim better).
  * NEVER evaluated on Hindi/Marathi speech. The 0.5 threshold is not
    calibrated. Never claim "100% deepfake detection".

FUTURE PRODUCT: fine-tuned/calibrated anti-spoofing evaluated on
Indian-language speech (roadmap phases A–C, §27).
"""
import logging
import shutil
from pathlib import Path

import numpy as np

from app.config import settings

log = logging.getLogger(__name__)

# Official AASIST-L model_config (config/AASIST-L.conf in the reference repo).
AASIST_L_CONFIG = {
    "architecture": "AASIST",
    "nb_samp": 64600,
    "first_conv": 128,
    "filts": [70, [1, 32], [32, 32], [32, 24], [24, 24]],
    "gat_dims": [24, 32],
    "pool_ratios": [0.4, 0.5, 0.7, 0.5],
    "temperatures": [2.0, 2.0, 100.0, 100.0],
}

NB_SAMPLES = 64600        # ~4.04 s at 16 kHz — official eval input length (§5)
SPOOF_THRESHOLD = 0.5     # UNCALIBRATED prototype decision cut — not tuned on any data

MODEL_LABEL = "aasist-l (pretrained, ASVspoof2019-LA, not validated on Hindi/Marathi)"


class VoiceDetector:
    """Operates on the audio SIGNAL, never the transcript (§5)."""

    has_model = True  # reported in /api/health

    def __init__(self) -> None:
        self.model = None
        self.model_loaded = False
        self.device = None

    # ------------------------------------------------------------------ setup

    def load_model(self) -> bool:
        """Called ONCE at startup (§19). Downloads the checkpoint if missing,
        loads it strictly (any mismatch = failure), eval mode, then warm-up
        forward pass so the first real request isn't slow (§24)."""
        if self.model_loaded:
            return True

        try:
            import torch
            from app.ml.aasist import Model
        except ImportError as exc:
            log.warning("VoiceDetector: torch not installed (%s) — staying in fallback mode", exc)
            return False

        try:
            path = Path(settings.VOICE_MODEL_PATH)
            if not path.is_file() or path.stat().st_size < 10_000:
                log.info("VoiceDetector: checkpoint missing at %s — downloading", path)
                if not self._download_weights(path):
                    log.warning("VoiceDetector: no checkpoint available — staying in fallback mode")
                    return False

            device = self._resolve_device(torch)
            model = Model(AASIST_L_CONFIG)
            state = torch.load(path, map_location="cpu")
            model.load_state_dict(state, strict=True)
            model.to(device).eval()

            # Warm-up: one forward pass on silence verifies shapes + speeds up
            # the first real request (§24: pre-warm at startup, not per-request).
            with torch.no_grad():
                _, logits = model(torch.zeros(1, NB_SAMPLES, device=device))
            if logits.shape != (1, 2):
                raise RuntimeError(f"Unexpected model output shape {tuple(logits.shape)}")

            self.model, self.device, self.model_loaded = model, device, True
            log.info("VoiceDetector: AASIST-L loaded on %s (warm-up done)", device)
            return True
        except Exception as exc:  # §20 — any load failure falls back, never crashes
            log.warning("VoiceDetector: load failed (%s) — staying in fallback mode", exc)
            self.model, self.model_loaded = None, False
            return False

    def _resolve_device(self, torch) -> "torch.device":
        """Honour settings.DEVICE, downgrading gracefully if unavailable."""
        want = settings.DEVICE.lower()
        if want.startswith("cuda") and not torch.cuda.is_available():
            log.warning("DEVICE=%s requested but CUDA unavailable — using cpu", want)
            return torch.device("cpu")
        if want == "mps" and not (hasattr(torch.backends, "mps") and torch.backends.mps.is_available()):
            log.warning("DEVICE=mps requested but MPS unavailable — using cpu")
            return torch.device("cpu")
        return torch.device(want)

    def _download_weights(self, dest: Path) -> bool:
        """Download the AASIST-L checkpoint (primary HF URL, then official
        GitHub fallback). Writes to a .part file first so a partial download
        is never mistaken for a working model."""
        import urllib.request

        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        for url in (settings.VOICE_MODEL_URL, settings.VOICE_MODEL_URL_FALLBACK):
            try:
                log.info("VoiceDetector: downloading weights from %s", url)
                with urllib.request.urlopen(url, timeout=120) as resp, open(tmp, "wb") as fh:
                    shutil.copyfileobj(resp, fh)
                tmp.rename(dest)
                log.info("VoiceDetector: weights saved to %s (%d bytes)", dest, dest.stat().st_size)
                return True
            except Exception as exc:
                log.warning("VoiceDetector: download failed from %s (%s)", url, exc)
        tmp.unlink(missing_ok=True)
        return False

    # --------------------------------------------------------------- inference

    def predict(self, audio, source_hint: str = "") -> dict:
        """
        Voice-authenticity prediction for one clip.

        `audio`: float waveform (np.ndarray), mono, 16 kHz — i.e. the
        "waveform" field of AudioProcessor.preprocess() output (route wiring
        comes with the analyze endpoints). Inputs are zero-padded / truncated
        to the official 64600-sample window.

        `source_hint` (demo only, e.g. a filename) routes the demo mock's
        canned values; the real model never reads it for scoring.

        Returns the frozen-contract `voice_trust` block, or the standard
        fallback shape — this method never raises (§20).
        """
        if self.model_loaded:
            try:
                return self._predict_real(audio)
            except Exception as exc:
                log.warning("VoiceDetector: inference failed (%s)", exc)
                if settings.DEMO_MODE:
                    return self._mock(source_hint)
                return {"status": "partial", "error": f"Voice inference failed: {exc}", "fallback_used": True}

        if settings.DEMO_MODE:
            return self._mock(source_hint)

        return {"status": "partial", "error": "Voice model unavailable", "fallback_used": True}

    def _predict_real(self, audio) -> dict:
        import torch
        import torch.nn.functional as F

        waveform = np.asarray(audio, dtype=np.float32).reshape(-1)
        if waveform.size == 0:
            return {"status": "partial", "error": "Empty waveform", "fallback_used": True}

        # Official eval protocol: keep the first ~4 s, zero-pad if shorter.
        x = np.zeros(NB_SAMPLES, dtype=np.float32)
        n = min(waveform.size, NB_SAMPLES)
        x[:n] = waveform[:n]

        with torch.no_grad():
            _, logits = self.model(torch.from_numpy(x).unsqueeze(0).to(self.device))
            probs = F.softmax(logits, dim=-1)[0]

        p_bonafide = float(probs[1])                       # official eval score: higher = genuine
        spoof_risk = round(1.0 - p_bonafide, 4)            # → 0–1 voice risk (0 = genuine)
        return {
            "spoof_risk": spoof_risk,
            # Identity layer has no real signal yet (Phase 16) — null, never invented.
            "speaker_mismatch_risk": None,
            "overall_voice_risk": spoof_risk,  # overall = f(spoof, identity); identity absent → spoof
            "status": "SUSPICIOUS" if spoof_risk >= SPOOF_THRESHOLD else "GENUINE",
            "model": MODEL_LABEL,
            "note": (
                f"Pretrained AASIST-L, ASVspoof2019-LA benchmark; threshold {SPOOF_THRESHOLD} "
                "uncalibrated; pretrained baseline, not yet evaluated on Indian-language "
                "speech (§5). PROTOTYPE."
            ),
        }

    def _mock(self, source_hint: str = "") -> dict:
        """§20/§DEMO — delegate to the shared demo mock (one mock, one truth)."""
        from app.demo import DemoVoiceDetector

        return DemoVoiceDetector().predict(source_hint=source_hint)
