"""
DEMO FALLBACK SYSTEM (§DEMO FALLBACK SYSTEM — "mandatory").

This package is the team's safety net: standalone, dependency-free mocks of
every intelligence service. They return realistic fake data that matches the
FROZEN CONTRACT exactly (verified by tests/test_demo.py against the Pydantic
models), so the full pipeline — and every future endpoint — runs even when
torch/transformers are broken, models can't download, or the demo laptop has
no GPU.

HARD RULES enforced here:
  * Pure stdlib only — importable in any environment, never the thing that
    breaks.
  * Every mock output carries model="mock_fallback" and a note containing
    "DEMO MODE". The UI must show "Prototype / Demo Analysis" for these —
    mock output is NEVER presented as real inference.
  * Deterministic: same input → same output, every run (§DEMO RELIABILITY).

DEMO HINTS (transparent, demo-only): mocks accept an optional `source_hint`
(usually the uploaded filename). Files whose names contain e.g. "scam"/"fake"
get the scam-scenario values, names containing "normal"/"casual" get the
normal-call values, everything else gets the §3 primary-demo values. This is
what makes the five demo scenarios reproducible with ZERO models installed.
It is a presentation aid, NOT inference — never imply otherwise.
"""
from app.demo.mock_asr import DemoASRService, NORMAL_SCRIPTS, SCAM_SCRIPTS
from app.demo.mock_scam_detector import DemoScamDetector
from app.demo.mock_speaker_verifier import DemoSpeakerVerifier
from app.demo.mock_voice_detector import DemoVoiceDetector

__all__ = [
    "DemoASRService",
    "DemoScamDetector",
    "DemoSpeakerVerifier",
    "DemoVoiceDetector",
    "NORMAL_SCRIPTS",
    "SCAM_SCRIPTS",
]
