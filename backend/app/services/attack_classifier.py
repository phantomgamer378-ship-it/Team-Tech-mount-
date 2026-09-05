"""
Attack-type classification (§ATTACK-TYPE CLASSIFICATION) — PURE LOOKUP.

`attack_types_from_indicators()` maps an indicator set (+ optional voice
evidence) to attack-type labels. This is NOT a model — deliberately (master
prompt: "This is NOT a separate ML model — do not build one"). A future
trained multi-label classifier can replace it behind the same function
signature without touching callers (roadmap phase E).

Multi-label by design: one interaction can be several attacks at once
(e.g. cloned voice + bank story + OTP ask).
"""
from typing import List, Optional

# Label set from the master prompt (§ATTACK-TYPE CLASSIFICATION examples).
AI_VOICE_LABEL = "AI Voice Impersonation"
SOCIAL_ENGINEERING_LABEL = "Social Engineering"


def attack_types_from_indicators(
    indicators: List[str],
    *,
    voice_spoof_risk: Optional[float] = None,
) -> List[str]:
    """Map matched scam indicators (+ voice evidence) to attack-type labels.

    Pure function: no I/O, no state, deterministic. `voice_spoof_risk` comes
    from the VoiceDetector (real or demo); >= 0.5 contributes the AI-voice
    label (0.5 = the prototype VoiceDetector threshold — one threshold, one
    source of truth).
    """
    ind = set(indicators or [])
    types: List[str] = []

    if voice_spoof_risk is not None and voice_spoof_risk >= 0.5:
        types.append(AI_VOICE_LABEL)

    if "Bank impersonation" in ind:
        types.append("Bank Fraud")
    if "Family-member impersonation" in ind:
        types.append("Family Emergency Scam")
    if "Police impersonation" in ind or "Executive impersonation" in ind:
        types.append("Authority Impersonation")
    if "OTP request" in ind:
        types.append("OTP Theft")
    if "Financial transfer request" in ind:
        types.append("Financial Fraud")
    if "Remote access request" in ind:
        types.append("Remote-Access Scam")
    if "Investment pitch" in ind:
        types.append("Investment Scam")
    if "Job-offer lure" in ind:
        types.append("Job Scam")
    if "Parcel/delivery lure" in ind:
        types.append("Parcel Scam")
    if "Secrecy request" in ind and types:
        types.append("Coercion & Secrecy")

    # Any matched indicator is, by construction, social engineering — but only
    # label it when at least one specific attack was identified.
    if types and ind:
        types.append(SOCIAL_ENGINEERING_LABEL)

    return types
