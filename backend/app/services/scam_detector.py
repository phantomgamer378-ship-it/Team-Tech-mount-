"""
ScamDetector — scam / social-engineering analysis of a transcript.
(Phase 5 keyword-based rule engine)

 transcript → rule/keyword/pattern match → scam_score + indicators.
"""
import re
from typing import Dict, List, Tuple
from app.config import settings

# Categories and their associated keywords (Hindi, Marathi, English/Code-mixed)
SCAM_RULES = {
    "OTP/PIN Request": [
        r"\botp\b", r"\bpin\b", r"\bpassword\b", r"\bpasscode\b", 
        r"पासवर्ड", r"ओटीपी", r"पिन", r"पासकोड", r"पासवर्ड",
        r"one time password",
    ],
    "Bank/KYC Impersonation": [
        r"\bkyc\b", r"\bbank\b", r"bank account", r"बँक", r"बैंक", 
        r"खाते", r"खाता", r"\bsbi\b", r"\bhdfc\b", r"\bicici\b",
        r"update your kyc", r"केवाईसी", r"आधार", r"pan card", r"पॅन", r"पैन"
    ],
    "Account Blocking Threat": [
        r"\bblock\b", r"\bclose\b", r"\bsuspend\b", r"बंद", r"ब्लॉक", 
        r"स्थगित", r"account will be blocked", r"अकाउंट बंद", r"खाते बंद"
    ],
    "Urgency / Time Pressure": [
        r"\burgent\b", r"\bnow\b", r"\bimmediately\b", r"\btoday\b", 
        r"लगेच", r"त्वरित", r"आत्ताच", r"तुरंत", r"अभी", r"आज ही", r"जल्दी"
    ],
    "Police / Authority Impersonation": [
        r"\bpolice\b", r"\bcbi\b", r"\bcustoms\b", r"\bfedex\b", r"\bdhl\b",
        r"पोलीस", r"पुलिस", r"अधिकारी", r"officer", r"custom officer", r"arrest"
    ],
    "Money Transfer Request": [
        r"\btransfer\b", r"\bpay\b", r"\bupi\b", r"\bgoogle pay\b", r"\bphonepe\b", r"\bpaytm\b",
        r"पैसे पाठवा", r"पैसे ट्रांसफर", r"रक्कम", r"पेमेंट", r"payment", r"send money",
        r"scan the qr", r"क्यूआर", r"स्कॅन"
    ],
    "Investment / Job / Parcel Scam": [
        r"\binvestment\b", r"\bcrypto\b", r"\bjob offer\b", r"\bparcel\b", r"\bpackage\b",
        r"गुंतवणूक", r"निवेश", r"नोकरी", r"नौकरी", r"पार्सल", r"पॅकेज", r"work from home"
    ],
    "Family Emergency": [
        r"\baccident\b", r"\bhospital\b", r"\bemergency\b", r"\barrested\b",
        r"अपघात", r"दवाखाना", r"रुग्णालय", r"अटक", r"एक्सीडेंट", r"अस्पताल", r"इमरजेंसी"
    ],
    "Credential / Info Request": [
        r"\bcvv\b", r"credit card", r"debit card", r"\batm\b", r"card number",
        r"क्रेडिट कार्ड", r"डेबिट कार्ड", r"एटीएम", r"कार्ड नंबर", r"expiry date"
    ]
}

# The §3 demo scripts
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
    has_model = False  # stateless rule engine

    def _match_rules(self, text: str) -> List[str]:
        text_lower = text.lower()
        matched_indicators = []
        
        for indicator, patterns in SCAM_RULES.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    matched_indicators.append(indicator)
                    break  # Move to next indicator category once matched
                    
        return matched_indicators
        
    def _calculate_score(self, indicators: List[str]) -> float:
        if not indicators:
            return 0.0
        # High impact indicators
        high_risk = {"OTP/PIN Request", "Credential / Info Request", "Money Transfer Request", "Account Blocking Threat", "Police / Authority Impersonation"}
        
        score = 0.0
        for ind in indicators:
            if ind in high_risk:
                score += 0.40
            else:
                score += 0.20
                
        return round(min(1.0, score), 2)

    def analyze(self, transcript: str) -> dict:
        """Analyze a transcript for scam indicators using regex rules."""
        if not transcript or not transcript.strip():
            return {
                "scam_score": 0.0,
                "category": "Unknown",
                "indicators": [],
            }
            
        matched_indicators = self._match_rules(transcript)
        score = self._calculate_score(matched_indicators)
        
        # Categorize the main threat
        category = "Unknown"
        if matched_indicators:
            if "Bank/KYC Impersonation" in matched_indicators:
                category = "Bank/KYC Fraud"
            elif "Police / Authority Impersonation" in matched_indicators:
                category = "Authority Impersonation Fraud"
            elif "Family Emergency" in matched_indicators:
                category = "Emergency Scam"
            elif "Investment / Job / Parcel Scam" in matched_indicators:
                category = "Advance Fee / Parcel Scam"
            else:
                category = "Suspicious Request"

        # Fallback to demo output if the user forced DEMO_MODE and no signals were found.
        # But if it's the demo script, it will naturally get scored high.
        if settings.DEMO_MODE and score == 0.0:
            return dict(DEMO_OUTPUT)

        return {
            "scam_score": score,
            "category": category,
            "indicators": matched_indicators,
            "model": "regex_rules_v1"
        }

