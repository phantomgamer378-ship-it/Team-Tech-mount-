"""
AudioProcessor — the §14 preprocessing pipeline shared by BOTH AI models.

Pipeline (each step explicit, in order):
    load → validate → mono → resample to 16 kHz → normalize → (chunk)

16 kHz mono is the one format that satisfies both AASIST (voice detector,
Phase 3) and IndicConformer (ASR, Phase 4), so a single pass serves both
models — preprocess once, reuse everywhere.

Never crashes (§20): every failure (missing file, corrupt bytes, wrong type,
too-short audio, missing library) returns the standard §13 fallback shape
{"status": "partial", "error": ..., "fallback_used": True}.

PROTOTYPE vs FUTURE PRODUCT: no real streaming and no VAD here. Phase 9
simulates real-time by sending 1-second chunks (see chunk()) over WebSocket.
A production system would stream, do VAD, and handle telephony 8 kHz codecs.
"""
import logging
from pathlib import Path
from typing import List, Optional

from app.config import settings

log = logging.getLogger(__name__)

# Guarded imports (§20 — a missing dependency must not crash the app):
try:
    import librosa
    import numpy as np
    import soundfile as sf

    DEPS_AVAILABLE = True
except ImportError:  # pragma: no cover - only hit on a broken environment
    DEPS_AVAILABLE = False

TARGET_SR = 16000        # shared by AASIST + IndicConformer (§14)
MIN_DURATION_S = 0.5     # below this, analysis is meaningless
SUPPORTED_SUFFIXES = {".wav", ".flac", ".ogg", ".mp3", ".aiff", ".aif"}
# NOTE: .m4a is NOT included — it needs ffmpeg. Tell users to convert to WAV.


class AudioProcessor:
    """Stateless preprocessing — no model to load (reports as such in /api/health)."""

    has_model = False

    # ------------------------------------------------------------------ API

    def preprocess(self, audio_path) -> dict:
        """
        Full pipeline for one audio file.

        Returns on success:
            {"ok": True, "status": "ok", "waveform": np.ndarray (float32, mono,
             peak-normalized), "sample_rate": 16000, "duration_s": float,
             "n_samples": int, "channels_in": int, "source_sr": int}
        Returns on ANY failure: the §13 fallback shape with ok=False.
        """
        if not DEPS_AVAILABLE:
            return self._fallback("Audio libraries not installed (pip install -r requirements.txt)")

        try:
            path = self._validated_path(audio_path)
            if isinstance(path, dict):  # validation failed → fallback dict
                return path

            # 1. LOAD (native sample rate; always_2d keeps channel handling uniform)
            data, source_sr = sf.read(path, dtype="float32", always_2d=True)

            if data.size == 0:
                return self._fallback("Audio file contains no samples")

            # 2. VALIDATE duration (cheap check before any resampling work)
            duration_in = data.shape[0] / source_sr
            if duration_in < MIN_DURATION_S:
                return self._fallback(
                    f"Audio too short: {duration_in:.2f}s (minimum {MIN_DURATION_S}s)"
                )

            # 3. MONO — average channels (prototype choice: simple and lossless enough)
            mono = self.to_mono(data)

            # 4. RESAMPLE to 16 kHz (no-op if already there)
            resampled = self.resample(mono, source_sr)

            # 5. NORMALIZE — simple peak normalization to full scale
            normalized = self.normalize(resampled)

            duration_s = len(normalized) / TARGET_SR
            return {
                "ok": True,
                "status": "ok",
                "waveform": normalized,
                "sample_rate": TARGET_SR,
                "duration_s": round(duration_s, 3),
                "n_samples": int(len(normalized)),
                "channels_in": int(data.shape[1]),
                "source_sr": int(source_sr),
            }
        except Exception as exc:  # §20 — corrupt/invalid audio must not crash us
            log.warning("Audio preprocessing failed for %s: %s", audio_path, exc)
            return self._fallback(f"Audio processing failed: {exc}")

    def to_mono(self, data: "np.ndarray") -> "np.ndarray":
        """(n_samples, n_channels) → (n_samples,). Multi-channel is averaged."""
        import numpy as np  # local: only reached when DEPS_AVAILABLE

        if data.ndim == 1:
            return data
        return np.mean(data, axis=1)

    def resample(self, waveform: "np.ndarray", source_sr: int) -> "np.ndarray":
        """Resample to TARGET_SR (soxr under the hood via librosa). No-op if equal."""
        if source_sr == TARGET_SR:
            return waveform.astype("float32", copy=False)
        return librosa.resample(
            waveform, orig_sr=source_sr, target_sr=TARGET_SR
        ).astype("float32", copy=False)

    def normalize(self, waveform: "np.ndarray") -> "np.ndarray":
        """Peak-normalize to [-1, 1]; pure silence is passed through unchanged."""
        peak = float(np.max(np.abs(waveform))) if waveform.size else 0.0
        if peak > 0:
            return (waveform / peak).astype("float32")
        return waveform.astype("float32", copy=False)

    def chunk(self, waveform: "np.ndarray", chunk_seconds: float = 1.0) -> List["np.ndarray"]:
        """
        Fixed-size contiguous slices (last one may be shorter — kept, not dropped).

        Phase 9 uses this to SIMULATE real-time streaming over WebSocket: send
        the chunks in order with a small delay. Not real streaming (§14/§15).
        """
        n = int(TARGET_SR * chunk_seconds)
        if n <= 0 or waveform.size == 0:
            return []
        return [waveform[i : i + n] for i in range(0, len(waveform), n)]

    # ------------------------------------------------------------- internals

    def _validated_path(self, audio_path) -> Path | dict:
        """Existence / size / extension checks. Returns a Path or a fallback dict."""
        path = Path(audio_path)

        if not path.is_file():
            return self._fallback(f"Audio file not found: {path}")

        max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
        size = path.stat().st_size
        if size == 0:
            return self._fallback(f"Audio file is empty: {path}")
        if size > max_bytes:
            return self._fallback(
                f"Audio file too large: {size / 1024 / 1024:.1f} MB (max {settings.MAX_UPLOAD_MB} MB)"
            )

        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            return self._fallback(
                f"Unsupported audio type '{path.suffix}'. Supported: "
                f"{sorted(s.lower() for s in SUPPORTED_SUFFIXES)}. "
                "For .m4a, convert to WAV first (it needs ffmpeg, which we don't ship)."
            )
        return path

    @staticmethod
    def _fallback(message: str) -> dict:
        """§13 standard fallback shape — the ONLY failure mode this class has."""
        return {"ok": False, "status": "partial", "error": message, "fallback_used": True}
