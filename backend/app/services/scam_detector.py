"""
ScamDetector — scam / social-engineering analysis of a transcript.
(Phase 1 placeholder; the rule engine lands in Phase 5.)

Phase 5 plan (§7): transcript → rule/keyword/pattern match → scam_score +
indicators. Indicators to cover:
  OTP/PIN request, bank/KYC impersonation, account-blocking threats, urgency,
  threats, police/authority impersonation, money-transfer requests,
  investment/job/parcel scams, family-emergency scams, requests for secrecy,
  credential requests.

Architecture rule (§7): callers depend only on this class — the rule engine
can later be swapped for a trained classifier without touching any caller.
No model to load: this is stateless by design.
"""
from app.config import settings

DEMO_OUTPUT = {
    "scam_score": 0.89,
    "category": "Bank/KYC Fraud",
    "indicators": [
        "Bank impersonation",
        "Account-blocking threat",
        "Urgency",
        "OTP request",
        "Financial risk",
    ],
    "model": "mock_fallback",
    "note": "DEMO MODE — not real inference (§20)",
}


class ScamDetector:
    has_model = False  # stateless rule engine — reported in /api/health

    def analyze(self, transcript: str) -> dict:
        """Analyze a transcript for scam indicators (§7).

        Phase 5 replaces the mock below with keyword/pattern rules. The empty
        transcript case already behaves like a real "no signal" result.
        """
        if not transcript or not transcript.strip():
            return {
                "scam_score": 0.0,
                "category": "Unknown",
                "indicators": [],
            }

        if settings.DEMO_MODE:
            return dict(DEMO_OUTPUT)

        # Rules not built yet (Phase 5) — fall back per §20, never crash.
        return {"status": "partial", "error": "Scam rules unavailable", "fallback_used": True}
