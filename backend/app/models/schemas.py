"""
API response contract (§13) — ONE consistent shape everywhere.

These Pydantic models are the contract between backend and Flutter. Services
can be swapped behind them, but field names and shapes must stay stable (§28).

Every analysis response also doubles as the fallback shape (§13): on any
failure a module returns status="partial" + error + fallback_used=true —
never a raw 500 (§20).
"""
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class VoiceAnalysis(BaseModel):
    """AI-voice/deepfake detector output — signal-level, not transcript-level (§5)."""

    ai_voice: bool = Field(description="True if the audio looks synthetic/spoofed")
    risk: float = Field(ge=0.0, le=1.0, description="0–1 voice-clone risk")
    confidence: float = Field(ge=0.0, le=1.0)
    model: Optional[str] = Field(default=None, description="Which detector produced this")
    note: Optional[str] = Field(default=None, description="e.g. 'DEMO MODE — not real inference'")


class ScamAnalysis(BaseModel):
    """Scam / social-engineering analysis of the transcript (§7)."""

    risk: float = Field(ge=0.0, le=1.0)
    category: str = "Unknown"
    indicators: List[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    """Fused 0–100 risk score (§8)."""

    score: int = Field(ge=0, le=100)
    level: Literal["LOW", "MEDIUM", "HIGH"]
    signals: Dict[str, float] = Field(default_factory=dict)


class LivenessInfo(BaseModel):
    """Liveness challenge state for HIGH-risk calls (§9)."""

    required: bool = False
    status: Literal["PENDING", "LIVE", "SUSPICIOUS", "FAILED"] = "PENDING"
    challenge: Optional[str] = None


class AnalysisResponse(BaseModel):
    """
    The §13 contract for the /api/analyze/* endpoints (wired in Phase 8).

    PROTOTYPE vs FUTURE PRODUCT: this shape stays stable while the models
    behind it are swapped or upgraded.
    """

    session_id: str
    status: Literal["ok", "partial"] = "ok"
    language: Optional[str] = None
    transcript: Optional[str] = None
    voice_analysis: Optional[VoiceAnalysis] = None
    scam_analysis: Optional[ScamAnalysis] = None
    risk: Optional[RiskAssessment] = None
    liveness: Optional[LivenessInfo] = None
    recommendation: Optional[str] = None
    fallback_used: bool = False
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """GET /api/health (§19 — health check from Phase 1)."""

    status: str = "ok"
    app: str
    version: str
    demo_mode: bool
    services: Dict[str, str] = Field(default_factory=dict)
