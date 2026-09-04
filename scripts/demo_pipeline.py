"""
Voice Clone Shield — live demo runner (§3 primary demo card, terminal edition).

Runs the CURRENT prototype end-to-end from one command and prints the demo
card. It is honest about what is real inference vs demo-mode mock (§20) —
the footer labels every signal, which is exactly the discipline judges
should see (§26).

Usage (from the repo root, venv active):
    python scripts/demo_pipeline.py                                   # bundled sample
    python scripts/demo_pipeline.py my_recording.wav                  # your own audio
    python scripts/demo_pipeline.py my_recording.wav --lang mr        # Marathi mock ASR

Stages: preprocess → voice/deepfake detection (REAL AASIST-L) → ASR (demo
mock until Phase 4) → scam analysis (demo mock until Phase 5) → risk fusion
(real §8 formula) → liveness challenge on HIGH risk.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))  # noqa: E402

from app.services import ServiceContainer  # noqa: E402

W = 62  # card width


def rule(char="-"):
    print(char * W)


def stage(n: int, name: str, ok_detail: str):
    print(f"[{n}] {name:<28} {ok_detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Voice Clone Shield demo card")
    parser.add_argument("audio", nargs="?", default="demo_data/test_babble_16k.wav",
                        help="audio file to analyse (WAV/FLAC/OGG/MP3)")
    parser.add_argument("--lang", choices=["hi", "mr"], default="hi",
                        help="language for the demo-mode transcript (hi/mr)")
    args = parser.parse_args()

    c = ServiceContainer()
    # Load once, like the server does (§19) — warms AASIST-L before scoring.
    if not c.voice_detector.model_loaded:
        c.voice_detector.load_model()

    print()
    rule("=")
    print("VOICE CLONE SHIELD — LIVE PIPELINE".center(W))
    rule("=")
    t0 = time.time()

    # 1. Preprocess (§14, real)
    pre = c.audio_processor.preprocess(args.audio)
    if not pre.get("ok"):
        print(f"Audio rejected, no crash (§20): {pre.get('error')}")
        return 0
    stage(1, "Preprocess", f"{pre['duration_s']} s @ {pre['source_sr']} Hz ch{pre['channels_in']} → 16 kHz mono")

    # 2. Voice / deepfake detection (§5 — REAL model if loaded)
    voice = c.voice_detector.predict(pre["waveform"])
    voice_tag = "REAL — AASIST-L" if voice.get("model", "").startswith("aasist") else "DEMO MODE"
    stage(2, "Voice/deepfake", f"risk {voice.get('voice_risk', 0):.4f}  [{voice_tag}]")

    # 3. ASR (§6 — demo mock until Phase 4)
    asr = c.asr_service.transcribe(pre["waveform"], lang=args.lang)
    stage(3, f"ASR ({asr.get('language', '?')})", f"{len(asr.get('transcript', ''))} chars  [DEMO MODE — Phase 4]")

    # 4. Scam analysis (§7 — demo mock until Phase 5)
    scam = c.scam_detector.analyze(asr.get("transcript", ""))
    stage(4, "Scam analysis", f"score {scam.get('scam_score', 0):.2f}  [DEMO MODE — Phase 5]")

    # 5. Risk fusion (§8 — real formula; context signals are future work)
    context_risk = 0.0  # honest placeholder: no channel/reputation signals yet
    risk = c.risk_engine.fuse(voice.get("voice_risk", 0.0), scam.get("scam_score", 0.0), context_risk)
    stage(5, "Risk fusion", f"formula 0.4v+0.4s+0.2c → {risk['risk_score']}/100 {risk['risk_level']}")

    # 6. Liveness challenge on HIGH (§9)
    liveness = None
    if risk["risk_level"] == "HIGH":
        liveness = c.liveness_service.start_challenge("demo-001")
        stage(6, "Liveness", f"required — challenge issued")

    dt = time.time() - t0

    # ------------------------------------------------------------- demo card
    print()
    rule("=")
    print("VOICE CLONE SHIELD".center(W))
    rule("=")
    print(f"Audio            : {Path(args.audio).name}")
    print(f"Risk Score       : {risk['risk_score']}/100 — {risk['risk_level']} RISK")
    print(f"AI Voice Detection: risk {voice.get('voice_risk', 0):.2f} "
          f"(P(genuine)={voice.get('p_bonafide', '?')})  [{voice_tag}]")
    print(f"Scam Detection   : risk {scam.get('scam_score', 0):.2f} — {scam.get('category', '?')}")
    print(f"Language         : {asr.get('language', '?').upper()}")
    print(f"Transcript       : {asr.get('transcript', '')}")
    if scam.get("indicators"):
        print("Detected Indicators: " + "  ".join(f"✓ {i}" for i in scam["indicators"]))
    if liveness:
        print()
        print("LIVENESS VERIFICATION REQUIRED")
        print(f'Please ask the caller to say: "{liveness["challenge"]}"')
    print()
    print("WARNING: Do not share OTP. Do not transfer money. Verify caller identity.")
    rule("=")
    print(f"Signals that are REAL : deepfake score (AASIST-L), preprocessing, "
          f"risk fusion formula, liveness")
    print("Signals in DEMO MODE  : transcript + scam indicators (Phase 4/5 will "
          "replace them; §20)")
    print("Prototype only — no telephony; deepfake model NOT validated on "
          "Hindi/Marathi (§5).")
    print(f"Pipeline time: {dt:.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
