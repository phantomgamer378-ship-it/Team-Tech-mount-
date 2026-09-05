"""
DemoScamDetector — mock of ScamDetector (§DEMO FALLBACK SYSTEM).

Returns the scam_analysis block of the frozen contract. A handful of obvious
keywords decides scam-vs-normal so the canned outputs line up with the other
mocks; the real rule engine (Phase 7) is far richer (concepts, hi/mr/en
patterns, weights). NOT intent analysis.
"""

SCAM_OUTPUT = {
    "risk": 0.89,  # §7 example value (internal name: intent_score)
    "category": "Bank/KYC Fraud",
    "indicators": [
        "Bank impersonation",
        "Account-blocking threat",
        "Urgency",
        "OTP request",
        "Financial risk",
    ],
}

NORMAL_OUTPUT = {
    "risk": 0.05,
    "category": "Normal conversation",
    "indicators": [],
}

# Deliberately tiny: enough to route canned outputs, nothing more.
_KEYWORDS = (
    "otp", "ओटीपी", "बैंक", "बँक", "खात", "पैस", "हजार", "रुपय",
    "accident", "अपघात", "transfer", "blocked", "बंद", "पासवर्ड", "password", "pin",
)


class DemoScamDetector:
    """Same interface as services.ScamDetector; keyword-routed canned output."""

    has_model = False  # stateless mock — reported as such in /api/health

    def load_model(self) -> bool:
        return False

    def analyze(self, transcript: str, source_hint: str = "") -> dict:
        text = (transcript or "").lower()
        if any(k in text for k in _KEYWORDS):
            out = dict(SCAM_OUTPUT)
        else:
            out = dict(NORMAL_OUTPUT)

        out["evidence"] = [
            f"[scam_rule] DEMO MODE — canned indicator '{i}' (no real analysis, §20)"
            for i in out["indicators"]
        ]
        out["model"] = "mock_fallback"
        out["note"] = (
            "DEMO MODE — not real inference. Canned §7 output routed by a "
            "tiny keyword list; the Phase 7 rule engine replaces this (§20)."
        )
        return out
