"""
DemoASRService — mock of ASRService (§DEMO FALLBACK SYSTEM).

Returns the ASR block of the frozen contract: language + a canned transcript.
NOT speech recognition. `confidence` is None on purpose — the contract forbids
hard-coding a confidence no model actually produced.
"""

# §3 demo scripts (scam scenarios) + normal-call controls for demo scenario 1.
SCAM_SCRIPTS = {
    "hi": "आपका बैंक अकाउंट बंद होने वाला है। अभी अपना OTP बताइए।",
    "mr": "तुमचे बँक खाते बंद होणार आहे. कृपया आत्ताच OTP सांगा.",
}
NORMAL_SCRIPTS = {
    "hi": "नमस्ते, सब ठीक है? चलो बाद में बात करते हैं।",
    "mr": "नमस्कार, सगळं ठीक आहे ना? नंतर बोलूया.",
}

_HINT_NORMAL = ("normal", "casual", "safe")


class DemoASRService:
    """Same interface as services.ASRService; transcripts are canned."""

    has_model = True
    model_loaded = False

    def load_model(self) -> bool:
        return False

    def transcribe(self, audio=None, lang: str = "hi", source_hint: str = "") -> dict:
        """`audio` is accepted for interface parity but never read — no
        speech recognition happens in demo mode."""
        language = lang if lang in SCAM_SCRIPTS else "hi"
        name = (source_hint or "").lower()
        if any(h in name for h in _HINT_NORMAL):
            transcript = NORMAL_SCRIPTS[language]
        else:  # default: the §3 primary demo script
            transcript = SCAM_SCRIPTS[language]

        return {
            "language": language,
            "transcript": transcript,
            "segments": [],           # honest: no model → no segments
            "confidence": None,       # honest: never hard-code a confidence
            "model": "mock_fallback",
            "note": (
                "DEMO MODE — not real inference. Canned §3 demo transcript "
                "selected by language + demo hint; no speech recognition "
                "happens (§20)."
            ),
        }

    def detect_language(self, audio, source_hint: str = "") -> str:
        return "hi"  # prototype default until real language id (Phase 5)
