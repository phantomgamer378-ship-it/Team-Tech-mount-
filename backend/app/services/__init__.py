"""
Service layer (§19, §MODEL ABSTRACTION) — one place that owns every service.

All app code gets services through ServiceContainer so that:
  * models load ONCE at startup, never per-request (§19);
  * any service can be swapped (rule-based → ML) without touching callers (§28);
  * USE_DEMO_SERVICES=true swaps in the app/demo/* mocks for EVERY service —
    the safety net that keeps the pipeline runnable with zero models.
"""
import logging
from dataclasses import dataclass, field

from app.config import settings
from app.risk.risk_engine import RiskEngine
from app.services.asr_service import ASRService
from app.services.audio_processor import AudioProcessor
from app.services.liveness_service import LivenessService
from app.services.scam_detector import ScamDetector
from app.services.voice_detector import VoiceDetector

log = logging.getLogger(__name__)


@dataclass
class ServiceContainer:
    voice_detector: VoiceDetector = field(default_factory=VoiceDetector)
    asr_service: ASRService = field(default_factory=ASRService)
    scam_detector: ScamDetector = field(default_factory=ScamDetector)
    risk_engine: RiskEngine = field(default_factory=RiskEngine)
    liveness_service: LivenessService = field(default_factory=LivenessService)
    audio_processor: AudioProcessor = field(default_factory=AudioProcessor)
    # Identity layer: stub until Phase 16 (returns null mismatch risk — honest).
    speaker_verifier: object = field(default_factory=lambda: _default_speaker_verifier())

    @classmethod
    def create(cls) -> "ServiceContainer":
        """Build the container — real services, or all-demo when configured.

        USE_DEMO_SERVICES (§DEMO FALLBACK SYSTEM): the whole pipeline runs on
        contract-valid mocks. Health still reports each mock as demo_mode and
        every mock output is labelled "DEMO MODE" — never shown as inference.
        """
        if settings.USE_DEMO_SERVICES:
            from app.demo import (
                DemoASRService,
                DemoScamDetector,
                DemoSpeakerVerifier,
                DemoVoiceDetector,
            )
            log.warning("USE_DEMO_SERVICES=true — wiring demo mocks for ALL services (§20)")
            return cls(
                voice_detector=DemoVoiceDetector(),
                asr_service=DemoASRService(),
                scam_detector=DemoScamDetector(),
                speaker_verifier=DemoSpeakerVerifier(),
            )
        return cls()

    def _all(self) -> dict:
        return {
            "voice_detector": self.voice_detector,
            "asr_service": self.asr_service,
            "scam_detector": self.scam_detector,
            "risk_engine": self.risk_engine,
            "liveness_service": self.liveness_service,
            "audio_processor": self.audio_processor,
            "speaker_verifier": self.speaker_verifier,
        }

    def load_all(self) -> None:
        """Load every model ONCE at startup (§19)."""
        for name, svc in self._all().items():
            loader = getattr(svc, "load_model", None)
            if loader is not None:
                loaded = loader()
                log.info("%s: model_loaded=%s", name, loaded)

    def status(self) -> dict:
        """Per-service state for /api/health."""
        report = {}
        for name, svc in self._all().items():
            if getattr(svc, "has_model", False):
                loaded = getattr(svc, "model_loaded", False)
                report[name] = (
                    "loaded" if loaded
                    else ("demo_mode" if settings.DEMO_MODE else "unavailable")
                )
            else:
                report[name] = "stateless"
        return report


def _default_speaker_verifier():
    """Real SpeakerVerifier lands in Phase 16; until then the demo stub is the
    honest default (null mismatch risk, explanatory note)."""
    from app.demo import DemoSpeakerVerifier

    return DemoSpeakerVerifier()
