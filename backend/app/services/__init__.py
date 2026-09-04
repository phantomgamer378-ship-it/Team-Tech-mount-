"""
Service layer (§19) — one place that owns every service instance.

All app code gets services through ServiceContainer so that:
  * models load ONCE at startup, never per-request (§19);
  * any service can be swapped (rule-based → ML) without touching callers (§28).
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

    def _all(self) -> dict:
        return {
            "voice_detector": self.voice_detector,
            "asr_service": self.asr_service,
            "scam_detector": self.scam_detector,
            "risk_engine": self.risk_engine,
            "liveness_service": self.liveness_service,
            "audio_processor": self.audio_processor,
        }

    def load_all(self) -> None:
        """Load every model ONCE at startup (§19). Phase 1: all placeholders."""
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
