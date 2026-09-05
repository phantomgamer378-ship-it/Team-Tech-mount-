"""
Analysis orchestration (§API responsibilities: "analysis orchestration") —
the ONE place that wires the full prototype pipeline. Two surfaces, one logic:

  * scripts/demo_pipeline.py  → terminal card, with live stage printing
  * POST /api/analyze/audio   → HTTP; no stage callback

Routes never reimplement pipeline logic — they prepare input (upload → temp
file), call analyze_audio(), persist the response, and enforce the contract.

Stages: preprocess → voice trust → ASR → scam intent → attack types →
fusion → Risk(t) timeline → policy → adaptive liveness.

Failure discipline (§20): the individual services never raise; this function
also never raises. A hard failure (e.g. unreadable audio) returns the bare
fallback shape; degraded signals produce status="partial" + fallback_used on
the canonical response, naming which signals degraded.
"""
import logging
from typing import Callable, Dict, List, Optional

from app.risk.policy_engine import decide, liveness_decision
from app.services import ServiceContainer
from app.services.attack_classifier import attack_types_from_indicators

log = logging.getLogger(__name__)

SR = 16000
VOICE_WINDOW_S = 4  # AASIST's native window — 1 s windows are out-of-distribution

RECOMMENDATIONS: Dict[str, str] = {
    "LOW": "No suspicious indicators detected. Stay alert for unexpected requests for money, codes or credentials.",
    "MEDIUM": "Stay cautious: do not share OTP/PIN or financial details; verify unexpected requests through official channels.",
    "HIGH": "Do not share OTP. Do not transfer money. Verify the caller through official channels before any action.",
    "CRITICAL": "Strong warning: do not share OTP, do not transfer money. End the interaction and verify via official channels.",
}


def analyze_audio(
    services: ServiceContainer,
    audio_path: str,
    session_id: str,
    lang: str = "hi",
    source_hint: str = "",
    on_stage: Optional[Callable[[int, str, str], None]] = None,
) -> Dict:
    """
    Run the full pipeline on one audio file.

    Returns {"response": <canonical AnalysisResponse dict | fallback dict>,
             "meta": <tags/policy for the demo card>}.
    """
    def stage(n: int, name: str, detail: str) -> None:
        if on_stage is not None:
            on_stage(n, name, detail)

    # 1. Preprocess -----------------------------------------------------------
    pre = services.audio_processor.preprocess(audio_path)
    if not pre.get("ok"):
        return {
            "response": {
                "status": "partial",
                "error": pre.get("error", "audio rejected"),
                "fallback_used": True,
            },
            "meta": {},
        }
    stage(1, "Preprocess",
          f"{pre['duration_s']} s @ {pre['source_sr']} Hz ch{pre['channels_in']} → 16 kHz mono")
    waveform = pre["waveform"]

    # 2. Voice trust ----------------------------------------------------------
    voice = services.voice_detector.predict(waveform, source_hint=source_hint)
    voice_ok = "spoof_risk" in voice
    voice_tag = "REAL — AASIST-L" if str(voice.get("model", "")).startswith("aasist") else "DEMO MODE"
    stage(2, "Voice trust",
          f"spoof {voice.get('spoof_risk', 0):.4f} {voice.get('status', '')}  [{voice_tag}]")

    # 3. ASR ------------------------------------------------------------------
    asr = services.asr_service.transcribe(waveform, lang=lang, source_hint=source_hint)
    asr_ok = isinstance(asr.get("transcript"), str)
    asr_tag = "REAL" if str(asr.get("model", "")) not in ("", "mock_fallback") else "DEMO MODE"
    stage(3, f"ASR ({asr.get('language', lang)})",
          f"{len(asr.get('transcript') or '')} chars  [{asr_tag}]")

    # 4. Scam intent ----------------------------------------------------------
    scam = services.scam_detector.analyze(asr.get("transcript") or "", source_hint=source_hint)
    scam_ok = "risk" in scam
    scam_tag = ("REAL — rule engine"
                if scam.get("model") == "rule_engine" and scam.get("note") is None
                else "DEMO MODE")
    stage(4, "Scam intent",
          f"score {scam.get('risk', 0):.2f} — {scam.get('category', '?')}  [{scam_tag}]")

    # 5. Attack types ---------------------------------------------------------
    attack_types = attack_types_from_indicators(
        scam.get("indicators") or [],
        voice_spoof_risk=voice.get("spoof_risk") if voice_ok else None,
    )
    stage(5, "Attack types", f"{len(attack_types)} label(s)  [pure lookup]")

    # 6. Fusion ---------------------------------------------------------------
    context_risk = 0.0  # honest placeholder: no channel/reputation signals yet
    risk = services.risk_engine.fuse(
        voice_risk=voice.get("spoof_risk") if voice_ok else None,
        scam_risk=scam.get("risk") if scam_ok else None,
        context_risk=context_risk,
    )
    stage(6, "Risk fusion", f"final {risk['risk_score']}/100 {risk['risk_level']}")

    # 7. Risk(t) timeline -----------------------------------------------------
    n_chunks = len(services.audio_processor.chunk(waveform, chunk_seconds=1.0))
    segments = asr.get("segments") or [] if asr_ok else []
    voice_risks: List[Optional[float]] = []
    scam_risks: List[Optional[float]] = []
    for i in range(n_chunks):
        window = waveform[i * SR : (i + VOICE_WINDOW_S) * SR]
        if window.size:
            voice_risks.append(
                services.voice_detector.predict(window, source_hint=source_hint).get("spoof_risk")
            )
        else:
            voice_risks.append(None)
        overlapping = " ".join(
            s.get("text", "") for s in segments
            if s.get("start", 0) < i + 1 and s.get("end", 1e9) > i
        )
        scam_risks.append(
            services.scam_detector.analyze(overlapping)["risk"] if overlapping.strip() else None
        )
    timeline = services.risk_engine.fuse_timeline(voice_risks, scam_risks, context_risk=context_risk)
    stage(7, "Risk timeline",
          f"{len(timeline)} pts: " + " → ".join(str(p["risk_score"]) for p in timeline))

    # 8. Policy ---------------------------------------------------------------
    action = decide(risk["risk_level"])
    lv_tier = liveness_decision(risk["risk_score"])
    stage(8, "Policy", f"{risk['risk_level']} → {action}")

    # 9. Adaptive liveness ----------------------------------------------------
    liveness_block: Dict = {"required": False, "status": None, "challenge": None}
    if lv_tier["required"]:
        started = services.liveness_service.start_challenge(session_id)
        liveness_block = {
            "required": True,
            "status": started["status"],
            "challenge": started["challenge"],
        }
        stage(9, "Liveness", f"{lv_tier['tier']} — challenge issued")

    # Explanation + recommendation (USP 9) ------------------------------------
    explanation: List[str] = []
    if voice_ok:
        explanation.append(
            f"[voice] Synthetic-voice evidence: spoof risk {voice['spoof_risk']:.2f} "
            f"→ {voice.get('status')} (source: {voice.get('model')})"
        )
    explanation.extend(scam.get("evidence") or [])
    explanation.append(
        f"[fused] Risk {risk['risk_score']}/100 ({risk['risk_level']}) — "
        f"weights used: {risk.get('weights_used')}"
    )
    explanation.append(f"[policy] {risk['risk_level']} → {action}")
    if liveness_block["required"]:
        explanation.append(f"[liveness] {lv_tier['tier']} challenge issued (fixed prototype phrase)")

    # Degradation bookkeeping (§20) ------------------------------------------
    fallbacks: List[str] = []
    if not voice_ok:
        fallbacks.append("voice model")
    if not asr_ok:
        fallbacks.append("ASR")
    if not scam_ok:
        fallbacks.append("scam rules")

    response = {
        "session_id": session_id,
        "status": "complete" if not fallbacks else "partial",
        "audio": {
            "duration": pre["duration_s"],
            "language": asr.get("language") if asr_ok else None,
        },
        "voice_trust": voice if voice_ok else None,
        "asr": asr if asr_ok else None,
        "scam_analysis": scam if scam_ok else None,
        "attack_types": attack_types,
        "risk": {"score": risk["risk_score"], "level": risk["risk_level"]},
        "risk_timeline": timeline,
        "liveness": liveness_block,
        "explanation": explanation,
        "recommendation": RECOMMENDATIONS[risk["risk_level"]],
        "fallback_used": bool(fallbacks),
        "error": f"degraded signals: {', '.join(fallbacks)}" if fallbacks else None,
    }
    meta = {
        "voice_tag": voice_tag,
        "asr_tag": asr_tag,
        "scam_tag": scam_tag,
        "policy_action": action,
        "liveness_tier": lv_tier["tier"],
        "pre": {k: pre[k] for k in ("duration_s", "source_sr", "channels_in")},
    }
    return {"response": response, "meta": meta}
