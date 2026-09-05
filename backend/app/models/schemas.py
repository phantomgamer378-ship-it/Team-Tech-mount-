"""
THE FROZEN API CONTRACT — single source of truth (v3 master prompt).

Every route response matches one of exactly two shapes:
  1. `AnalysisResponse` (canonical success, §API RESPONSE CONTRACT)
  2. `FallbackResponse` ({"status":"partial","error","fallback_used":true})
A raw 500/stack trace must never reach a client — services return data that
fits these models or the fallback.

CONTRACT RULES (do not break without team sign-off):
  * `voice_trust` replaces the old `voice_analysis`; identity risk is null
    until a real speaker-verification signal exists — never fabricate it.
  * `asr.confidence` is set ONLY when the model actually provides it —
    never hard-code a confidence value (master prompt rule).
  * Risk levels are 4 tiers: LOW 0–39 · MEDIUM 40–69 · HIGH 70–84 ·
    CRITICAL 85–100 (prototype bands, aligned with liveness tiers).
  * Liveness states: PENDING / PASSED / SUSPICIOUS / FAILED.
  * `explanation[]` strings are source-tagged: [voice] [scam_rule]
    [identity] [fused] — this is the explainable-evidence contract.
"""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# ------------------------------------------------------------------ literals

RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
LivenessState = Literal["PENDING", "PASSED", "SUSPICIOUS", "FAILED"]
VoiceTrustStatus = Literal["GENUINE", "SUSPICIOUS"]
EvidenceSource = Literal["voice", "scam_rule", "identity", "context", "liveness", "fused"]


# ------------------------------------------------------------- sub-models

class AudioInfo(BaseModel):
    """Metadata about the analysed audio. Never the audio itself (privacy)."""

    duration: float = Field(description="seconds")
    language: Optional[str] = Field(default=None, description="'hi' | 'mr' | code-mix tag")


class VoiceTrust(BaseModel):
    """Multi-signal voice authenticity block (USP 1).

    speaker_mismatch_risk stays null until the identity layer has a real
    signal (Phase 16) — a missing signal is honest; an invented one is not.
    """

    spoof_risk: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    speaker_mismatch_risk: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    overall_voice_risk: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    status: Optional[VoiceTrustStatus] = None
    model: Optional[str] = Field(default=None, description="e.g. 'aasist-l' or 'mock_fallback'")
    note: Optional[str] = None


class ASRInfo(BaseModel):
    """Speech understanding block (USP 3)."""

    language: Optional[str] = None
    transcript: Optional[str] = None
    segments: List[Dict[str, Any]] = Field(default_factory=list)
    confidence: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="ONLY when the model provides it — never hard-coded",
    )
    model: Optional[str] = None
    note: Optional[str] = None


class ScamAnalysis(BaseModel):
    """Scam-intent block (USP 4). Internal score name: intent_score.

    `evidence` is additive-optional beyond the frozen example: matched-pattern
    lines that feed the source-tagged `explanation[]` (USP 9)."""

    risk: float = Field(default=0.0, ge=0.0, le=1.0)
    category: str = "Unknown"
    indicators: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    model: Optional[str] = None
    note: Optional[str] = None


class RiskAssessment(BaseModel):
    """Fused 0–100 score (USP 2)."""

    score: int = Field(ge=0, le=100)
    level: RiskLevel


class LivenessInfo(BaseModel):
    """Adaptive liveness block (USP 6).

    `challenge` is additive-optional beyond the frozen example: the UI needs
    the phrase to display; the /api/liveness/start endpoint also returns it.
    """

    required: bool = False
    status: Optional[LivenessState] = None
    challenge: Optional[str] = None


class RiskTimelinePoint(BaseModel):
    """One entry of risk(t) — the dynamic-risk demo moment (USP 2)."""

    t: float = Field(description="seconds into the audio")
    voice_risk: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    scam_risk: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    risk_score: int = Field(ge=0, le=100)
    level: RiskLevel


class EvidenceRecord(BaseModel):
    """Normalized evidence (§EVIDENCE NORMALIZATION) — one schema for every
    signal regardless of originating model; score semantics documented at the
    producing adapter, never mixed raw logits with probabilities."""

    signal: str
    score: Optional[float] = None
    direction: Literal["risk", "safe", "neutral"] = "risk"
    source: str = Field(description="producing adapter, e.g. 'aasist' | 'scam_rule' | 'fused'")
    timestamp: Optional[float] = None
    confidence: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ------------------------------------------------------------ responses

class AnalysisResponse(BaseModel):
    """
    Canonical success shape for /api/analyze/audio.

    status="complete" — full pipeline ran.
    status="partial"  — pipeline completed with degraded signals
                        (fallback_used=true names which); hard failures use
                        the bare FallbackResponse instead.
    """

    session_id: str
    status: Literal["complete", "partial"] = "complete"

    audio: Optional[AudioInfo] = None
    voice_trust: Optional[VoiceTrust] = None
    asr: Optional[ASRInfo] = None
    scam_analysis: Optional[ScamAnalysis] = None
    attack_types: List[str] = Field(default_factory=list)

    risk: Optional[RiskAssessment] = None
    risk_timeline: List[RiskTimelinePoint] = Field(default_factory=list)

    liveness: Optional[LivenessInfo] = None
    explanation: List[str] = Field(default_factory=list)
    recommendation: Optional[str] = None

    fallback_used: bool = False
    error: Optional[str] = None


class FallbackResponse(BaseModel):
    """The ONE failure shape — returned by every module on any failure (§20)."""

    status: Literal["partial"] = "partial"
    error: str
    fallback_used: bool = True


class SessionCreateRequest(BaseModel):
    """POST /api/session body."""

    source: str = "upload"


class SessionResponse(BaseModel):
    """POST /api/session."""

    session_id: str
    created_at: str
    source: Optional[str] = None


class LivenessStartRequest(BaseModel):
    session_id: str


class LivenessStartResponse(BaseModel):
    """POST /api/liveness/start."""

    session_id: str
    required: bool = True
    status: LivenessState = "PENDING"
    challenge: str


class LivenessVerifyRequest(BaseModel):
    session_id: str
    spoken_text: str = ""


class LivenessVerifyResponse(BaseModel):
    """POST /api/liveness/verify."""

    session_id: str
    status: LivenessState
    challenge: Optional[str] = None
    note: Optional[str] = None


class HistoryResponse(BaseModel):
    """GET /api/history — persisted analysis results (metadata only, no audio)."""

    history: List[Dict[str, Any]] = Field(default_factory=list)
    count: int = 0


class HealthResponse(BaseModel):
    """GET /api/health — per-service state + storage + privacy mode (§OBSERVABILITY)."""

    status: str = "ok"
    app: str
    version: str
    demo_mode: bool
    privacy_mode: bool = True
    database: str = Field(default="unknown", description="connected | unavailable | unknown")
    services: Dict[str, str] = Field(default_factory=dict)
