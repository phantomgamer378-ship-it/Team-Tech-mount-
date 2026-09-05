"""
DemoSpeakerVerifier — stub of the future SpeakerVerifier (§TRUSTED VOICE
MEMORY). The identity layer has NO real signal in the prototype, so the only
honest value for speaker_mismatch_risk is null. The contract requires this —
a missing signal is honest; an invented one is not.

The conceptual enrollment flow (user → sample → embedding → reference →
compare) is documented in docs/architecture.md §8; the endpoint flow arrives
in Phase 16. Never claim "voice match proves identity" — it is one signal.
"""


class DemoSpeakerVerifier:
    has_model = False

    def load_model(self) -> bool:
        return False

    def compare(self, audio, profile=None) -> dict:
        return {
            "speaker_mismatch_risk": None,
            "matched_profile": None,
            "model": "stub",
            "note": (
                "Identity signal not implemented in the prototype (Phase 16). "
                "speaker_mismatch_risk is null — a missing signal, not a "
                "neutral one. Voice identity alone never proves identity."
            ),
        }
