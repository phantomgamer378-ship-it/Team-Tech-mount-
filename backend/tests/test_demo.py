"""
Phase 4 tests — the app/demo/* mock package (§DEMO FALLBACK SYSTEM).

The mocks are the team's safety net: these tests prove they (a) always emit
frozen-contract-valid data, (b) are deterministic, (c) carry the mandatory
"DEMO MODE" / mock_fallback labels, and (d) can drive a complete
AnalysisResponse end-to-end with zero models installed.

Run from backend/:  python -m pytest -v
"""
import pytest
from pydantic import ValidationError

from app.config import settings
from app.demo import (
    NORMAL_SCRIPTS,
    SCAM_SCRIPTS,
    DemoASRService,
    DemoScamDetector,
    DemoSpeakerVerifier,
    DemoVoiceDetector,
)
from app.models.schemas import AnalysisResponse, ASRInfo, ScamAnalysis, VoiceTrust
from app.risk.risk_engine import RiskEngine
from app.services import ServiceContainer
from app.services.liveness_service import LivenessService


# ------------------------------------------------------------ individual mocks

def test_demo_voice_matches_frozen_contract():
    out = DemoVoiceDetector().predict(source_hint="hindi_scam.wav")
    vt = VoiceTrust(**out)  # raises if any key/shape deviates from the contract
    assert vt.spoof_risk == 0.93 and vt.status == "SUSPICIOUS"
    assert vt.speaker_mismatch_risk is None       # honest absence (Phase 16)
    assert out["model"] == "mock_fallback"
    assert "DEMO MODE" in out["note"]


def test_demo_voice_hint_routing():
    vd = DemoVoiceDetector()
    scam = vd.predict(source_hint="fake_marathi.wav")
    normal = vd.predict(source_hint="normal_conversation.wav")
    no_hint = vd.predict()                        # default = primary demo
    assert (scam["spoof_risk"], no_hint["spoof_risk"]) == (0.93, 0.93)
    assert normal["spoof_risk"] == 0.06 and normal["status"] == "GENUINE"


def test_demo_asr_matches_frozen_contract():
    out = DemoASRService().transcribe(lang="mr", source_hint="marathi_scam.wav")
    block = ASRInfo(**out)
    assert block.language == "mr"
    assert block.transcript == SCAM_SCRIPTS["mr"]
    assert block.segments == []
    assert block.confidence is None               # never hard-code a confidence
    assert out["model"] == "mock_fallback" and "DEMO MODE" in out["note"]


def test_demo_asr_normal_hint_and_determinism():
    asr = DemoASRService()
    a = asr.transcribe(lang="hi", source_hint="normal_hindi_chat.wav")
    b = asr.transcribe(lang="hi", source_hint="normal_hindi_chat.wav")
    assert a == b                                 # deterministic (§DEMO RELIABILITY)
    assert a["transcript"] == NORMAL_SCRIPTS["hi"]


def test_demo_scam_matches_frozen_contract():
    out = DemoScamDetector().analyze("your bank account will be blocked, share the OTP")
    block = ScamAnalysis(**out)
    assert block.risk == 0.89
    assert block.category == "Bank/KYC Fraud"
    assert "OTP request" in block.indicators
    assert out["model"] == "mock_fallback" and "DEMO MODE" in out["note"]


def test_demo_scam_normal_transcript_scores_low():
    out = DemoScamDetector().analyze("namaste, how was your day, see you later")
    assert out["risk"] == 0.05
    assert out["indicators"] == []


def test_demo_speaker_verifier_is_an_honest_stub():
    out = DemoSpeakerVerifier().compare(audio=None)
    assert out["speaker_mismatch_risk"] is None   # no invented identity signal
    assert "Phase 16" in out["note"]


# --------------------------------------------- full pipeline assembled on mocks

def _run_mock_pipeline() -> AnalysisResponse:
    """Exactly the call sequence the future /api/analyze/audio route will use —
    with every intelligence service mocked (USE_DEMO_SERVICES mode)."""
    vd = DemoVoiceDetector()
    asr = DemoASRService()
    scam = DemoScamDetector()

    voice = vd.predict(source_hint="hindi_scam.wav")
    transcript = asr.transcribe(lang="hi", source_hint="hindi_scam.wav")
    scam_out = scam.analyze(transcript["transcript"], source_hint="hindi_scam.wav")

    fused = RiskEngine().fuse(
        voice["spoof_risk"], scam_out["risk"], context_risk=0.0
    )
    liveness = (
        LivenessService().start_challenge("sess-test")
        if fused["risk_level"] == "HIGH" else None
    )

    return AnalysisResponse(
        session_id="sess-test",
        audio={"duration": 4.0, "language": transcript["language"]},
        voice_trust=voice,
        asr=transcript,
        scam_analysis=scam_out,
        attack_types=["AI Voice Impersonation", "Bank Fraud"],
        risk={"score": fused["risk_score"], "level": fused["risk_level"]},
        liveness={"required": liveness is not None,
                  "status": "PENDING" if liveness else None,
                  "challenge": liveness["challenge"] if liveness else None},
        explanation=[
            "[voice] Demo mock spoof evidence",
            "[scam_rule] Demo mock indicators",
            "[fused] Prototype weighted fusion",
        ],
        recommendation="Do not share OTP or transfer money.",
        fallback_used=True,
    )


def test_full_pipeline_on_mocks_produces_canonical_response():
    resp = _run_mock_pipeline()
    # Phase 9 renormalized weights: voice+scam+context present →
    # (0.93+0.89)*0.3/0.7 = 0.78 → 78 (identity/liveness excluded, not invented)
    assert resp.risk.level == "HIGH"
    assert resp.risk.score == 78
    assert resp.liveness.required is True     # HIGH → liveness challenge
    assert resp.status == "partial" or resp.status == "complete"
    # The route would override status — here we assert the shape only.
    dumped = resp.model_dump()
    assert dumped["voice_trust"]["spoof_risk"] == 0.93
    assert dumped["asr"]["transcript"] == SCAM_SCRIPTS["hi"]


def test_full_pipeline_on_mocks_is_deterministic():
    a, b = _run_mock_pipeline(), _run_mock_pipeline()
    assert a.model_dump() == b.model_dump()


# ------------------------------------------------------------ container switch

def test_use_demo_services_swaps_every_service(monkeypatch):
    monkeypatch.setattr(settings, "USE_DEMO_SERVICES", True)
    c = ServiceContainer.create()
    from app.demo import DemoASRService, DemoScamDetector, DemoSpeakerVerifier

    assert isinstance(c.voice_detector, DemoVoiceDetector)
    assert isinstance(c.asr_service, DemoASRService)
    assert isinstance(c.scam_detector, DemoScamDetector)
    assert isinstance(c.speaker_verifier, DemoSpeakerVerifier)
    # Health reporting: mocks with a model slot show demo_mode, others stateless
    assert c.status()["voice_detector"] == "demo_mode"
    assert c.status()["scam_detector"] == "stateless"


def test_default_container_uses_real_services(monkeypatch):
    monkeypatch.setattr(settings, "USE_DEMO_SERVICES", False)
    c = ServiceContainer.create()
    from app.services import ASRService, ScamDetector, VoiceDetector

    assert isinstance(c.voice_detector, VoiceDetector)
    assert isinstance(c.asr_service, ASRService)
    assert isinstance(c.scam_detector, ScamDetector)


# ------------------------------------------------------ label discipline (§20)

@pytest.mark.parametrize("out", [
    DemoVoiceDetector().predict(),
    DemoASRService().transcribe(),
    DemoScamDetector().analyze("blocked account, send OTP"),
])
def test_every_mock_output_is_labelled(out):
    assert out["model"] == "mock_fallback"
    assert "DEMO MODE" in out["note"]
