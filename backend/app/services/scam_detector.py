"""
ScamDetector — scam / social-engineering analysis of a transcript (§7).
Phase 7: the REAL rule engine (deterministic, dependency-free — always runs,
no model-loading discipline needed; §DEMO FALLBACK still covers it via
USE_DEMO_SERVICES for pipeline-wide mock runs).

Design (§SCAM INTENT DETECTION — "do NOT depend only on keywords"):
  transcript → normalize ASR spelling variants → concept detection (14
  concepts via patterns across Hindi/Marathi/English/code-mixed) →
  transparent weighted score + category + evidence lines.

Concepts (master prompt §SCAM INTENT DETECTION): urgency, threat, secrecy,
authority impersonation, family-member impersonation, banking/KYC, OTP/PIN/
password request, financial transfer, investment, job scam, parcel scam,
police/legal threat, account suspension, remote access, identity pressure.

Scoring is PROTOTYPE-ONLY: fixed additive weights, clamped to [0,1]. These
are demo weights — never claim calibration (roadmap phase E replaces this
with a trained classifier).

Spelling-variant normalization: faster-whisper (small) transcribes Indic
speech phonetically (e.g. OTP → 'अटीपी', बंद → 'बन्द'). A small canonical
map folds common variants back before matching. Keep additions honest:
only add variants actually observed in evaluation.

Callers depend only on this class — swap for a trained classifier without
touching any caller (§7).
"""
import logging
import re
from typing import Dict, List, Tuple

log = logging.getLogger(__name__)

MODEL_NAME = "rule_engine"

# --------------------------------------------------------------------------
# ASR spelling-variant normalization (observed faster-whisper-small outputs).
# Applied once, in order, on a whitespace-collapsed copy of the transcript.
SPELLING_VARIANTS: Tuple[Tuple[str, str], ...] = (
    ("अटीपी", "ओटीपी"),
    ("अटी पी", "ओटीपी"),
    ("ओ टी पी", "ओटीपी"),
    ("ती पी", "ओटीपी"),
    ("o.t.p", "otp"),
    ("बन्द", "बंद"),
    ("अकाून्त", "अकाउंट"),
    ("अकौंट", "अकाउंट"),
    ("अकाउन्ट", "अकाउंट"),
    ("टीक", "ठीक"),
    ("क्रुपया", "कृपया"),
    ("तुम्चे", "तुमचे"),
)

# --------------------------------------------------------------------------
# Concept table: (concept_id, indicator display name, prototype weight,
#                 [regex patterns over the normalized transcript]).
# Weights are DEMO weights (§7) — transparent, not validated.
CONCEPTS: List[Tuple[str, str, float, List[str]]] = [
    ("otp_credential", "OTP request", 0.35, [
        r"ओटीपी", r"\botp\b", r"पासवर्ड", r"\bpassword\b", r"\bpin\b", r"सीवीवी", r"\bcvv\b",
    ]),
    ("financial_transfer", "Financial transfer request", 0.30, [
        r"पैस", r"रुपय", r"ट्रांसफर", r"\btransfer\b", r"भेज", r"पाठव",
        r"हजार", r"लाख", r"\bmoney\b",
    ]),
    ("bank_impersonation", "Bank impersonation", 0.25, [
        r"बैंक", r"बँक", r"\bbank\b", r"\bkyc\b", r"केवाईसी",
    ]),
    ("family_impersonation", "Family-member impersonation", 0.25, [
        r"आई[,\. ]", r"माँ[,\. ]", r"पापा", r"बाबा", r"भैया", r"दादा",
        r"\bmom\b", r"\bdad\b", r"\bmummy\b", r"\bpapa\b",
    ]),
    ("police_threat", "Police impersonation", 0.25, [
        r"पुलिस", r"\bpolice\b", r"सीबीआई", r"\bcbi\b", r"कोर्ट", r"\bcourt\b", r"जेल", r"कानून",
    ]),
    ("remote_access", "Remote access request", 0.25, [
        r"रिमोट", r"स्क्रीन", r"anydesk", r"teamviewer", r"आपके फोन", r"फोन में", r"फोन पर",
    ]),
    ("executive_impersonation", "Executive impersonation", 0.20, [
        r"\bceo\b", r"\bboss\b", r"मालिक", r"डायरेक्टर", r"\bdirector\b",
    ]),
    ("suspension_threat", "Account-blocking threat", 0.20, [
        r"(खात\w*|अकाउंट|account)\s*\w*\s*(बंद|ब्लॉक|blocked)",
        r"बंद होने वाला", r"बंद होणार", r"\bblocked\b", r"ब्लॉक",
    ]),
    ("secrecy", "Secrecy request", 0.20, [
        r"किसी को (मत|नहीं) बता", r"किसी को नहीं", r"गोपनीय", r"कोणाला सांगू", r"कोणाला नको",
        r"don'?t tell", r"\bsecret\b", r"सांगू नका",
    ]),
    ("investment", "Investment pitch", 0.20, [
        r"निवेश", r"\binvestment\b", r"शेयर बाजार", r"\bstock\b", r"म्यूचुअल",
        r"\bmutual fund\b", r"क्रिप्टो", r"\bcrypto\b", r"डबल",
    ]),
    ("urgency", "Urgency", 0.15, [
        r"अभी", r"तुरंत", r"जल्दी", r"लगेच", r"\bimmediately\b", r"\burgent\b",
        r"\btoday\b", r"आज",
    ]),
    ("emergency_claim", "Emergency claim", 0.15, [
        r"\baccident\b", r"एक्सीडेंट", r"अपघात", r"दुर्घटना", r"हॉस्पिटल",
        r"\bhospital\b", r"भर्ती",
    ]),
    ("job_lure", "Job-offer lure", 0.15, [
        r"नौकरी", r"\bjob\b", r"रोजगार", r"work.?from.?home", r"भर्ती",
    ]),
    ("parcel_lure", "Parcel/delivery lure", 0.15, [
        r"पार्सल", r"\bparcel\b", r"कूरियर", r"\bcourier\b", r"डिलीवरी",
        r"\bdelivery\b", r"शिपमेंट",
    ]),
]

# --------------------------------------------------------------------------
# Category assignment: first rule whose primary concepts all matched AND
# whose secondary concepts (if any) have at least one match wins.
CATEGORY_RULES: List[Tuple[List[str], List[str], str]] = [
    (["bank_impersonation"], ["otp_credential", "financial_transfer", "suspension_threat"], "Bank/KYC Fraud"),
    (["family_impersonation"], ["financial_transfer", "urgency", "emergency_claim"], "Family Emergency Scam"),
    (["police_threat"], [], "Police/Legal Threat"),
    (["remote_access"], ["otp_credential", "bank_impersonation"], "Remote-Access Scam"),
    (["executive_impersonation"], ["financial_transfer"], "Executive Impersonation"),
    (["investment"], [], "Investment Scam"),
    (["job_lure"], [], "Job Scam"),
    (["parcel_lure"], [], "Parcel/Delivery Scam"),
]

GENERIC_SUSPICIOUS_CATEGORY = "Suspicious conversation"
NORMAL_CATEGORY = "Normal conversation"


class ScamDetector:
    """Stateless rule engine — `has_model=False`; deterministic; never raises."""

    has_model = False  # reported in /api/health

    def analyze(self, transcript: str, source_hint: str = "") -> dict:
        """Analyze a transcript → frozen-contract scam_analysis block.

        `source_hint` is accepted for interface parity with the demo mock and
        ignored by the rule engine — matching is content-only (§7).
        """
        if not transcript or not transcript.strip():
            return {
                "risk": 0.0,
                "category": NORMAL_CATEGORY,
                "indicators": [],
                "evidence": [],
                "model": MODEL_NAME,
                "note": None,
            }

        text = self._normalize(transcript)

        matched: Dict[str, Tuple[str, str]] = {}  # concept_id -> (display, snippet)
        for concept_id, display, _weight, patterns in CONCEPTS:
            for pattern in patterns:
                m = re.search(pattern, text, flags=re.IGNORECASE)
                if m:
                    matched[concept_id] = (display, m.group(0))
                    break  # one snippet per concept

        score = min(1.0, sum(w for cid, _d, w, _p in CONCEPTS if cid in matched))
        indicators = [matched[cid][0] for cid, _d, _w, _p in CONCEPTS if cid in matched]
        category = self._category(matched, score)
        evidence = [
            f"[scam_rule] {display} — matched '{snippet[:40]}'"
            for cid, (display, snippet) in sorted(matched.items())
        ]

        return {
            "risk": round(score, 4),
            "category": category,
            "indicators": indicators,
            "evidence": evidence,
            "model": MODEL_NAME,
            "note": None,  # None == real analysis (demo mocks set a DEMO MODE note)
        }

    # ------------------------------------------------------------- internals

    @staticmethod
    def _normalize(transcript: str) -> str:
        text = re.sub(r"\s+", " ", str(transcript)).strip().lower()
        for variant, canonical in SPELLING_VARIANTS:
            text = text.replace(variant, canonical)
        return text

    @staticmethod
    def _category(matched: Dict[str, Tuple[str, str]], score: float) -> str:
        for primaries, secondaries, label in CATEGORY_RULES:
            if not set(primaries) <= set(matched):
                continue
            if secondaries and not set(secondaries) & set(matched):
                continue
            return label
        return GENERIC_SUSPICIOUS_CATEGORY if matched else NORMAL_CATEGORY
