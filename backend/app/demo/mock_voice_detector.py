"""
DemoVoiceDetector — mock of VoiceDetector (§DEMO FALLBACK SYSTEM).

Returns the VoiceTrust block of the frozen contract. Deterministic, driven by
the optional demo hint (see app/demo/__init__.py). NOT inference: no audio is
analysed in any way.
"""

# §3/§7 primary-demo values (what the master prompt's example card shows).
SCAM_SPOOF_RISK = 0.93
SAFE_SPOOF_RISK = 0.06

_HINT_SCAM = ("scam", "fake", "clone", "synthetic", "tts", "fraud", "attack")
_HINT_SAFE = ("normal", "real", "genuine", "casual")


class DemoVoiceDetector:
    """Same interface as services.VoiceDetector; every value is fabricated."""

    has_model = True   # reported by /api/health like the real one
    model_loaded = False  # and, like an unavailable model, stays "demo_mode"

    def load_model(self) -> bool:
        return False  # nothing to load — by design

    def predict(self, audio=None, source_hint: str = "") -> dict:
        """`audio` is accepted for interface parity but never read — no
        analysis happens in demo mode."""
        name = (source_hint or "").lower()
        if any(h in name for h in _HINT_SAFE):
            spoof, status = SAFE_SPOOF_RISK, "GENUINE"
        else:  # scam hints AND the no-hint default both show the primary demo
            spoof, status = SCAM_SPOOF_RISK, "SUSPICIOUS"

        return {
            "spoof_risk": spoof,
            # Identity layer has no signal yet (Phase 16) — null, never invented.
            "speaker_mismatch_risk": None,
            "overall_voice_risk": spoof,
            "status": status,
            "model": "mock_fallback",
            "note": (
                "DEMO MODE — not real inference. Value chosen from the demo "
                "hint (filename), no audio analysis happens (§20)."
            ),
        }
