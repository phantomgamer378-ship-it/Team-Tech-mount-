"""
Generate TTS speech samples for ASR validation and demo scenarios (§21).

Usage (from repo root, venv active):
    pip install gTTS        # one-off tool, NOT a runtime dependency (§28)
    python scripts/generate_tts_samples.py

Creates in demo_data/ (all clearly labelled TTS — see demo_data/README.md):
    tts_hindi_scam.mp3       §3 Hindi scam script
    tts_marathi_scam.mp3     §3 Marathi scam script
    tts_hindi_normal.mp3     normal-call control (demo scenario 1)

These are SYNTHETIC voices — perfect for validating the ASR path end-to-end
and for demos, but be explicit with judges that they are TTS, not recordings.
"""
import sys
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "demo_data"

SCRIPTS = {
    "tts_hindi_scam.mp3": ("hi",
                           "आपका बैंक अकाउंट बंद होने वाला है। अभी अपना OTP बताइए।"),
    "tts_marathi_scam.mp3": ("mr",
                             "तुमचे बँक खाते बंद होणार आहे. कृपया आत्ताच OTP सांगा."),
    "tts_hindi_normal.mp3": ("hi",
                             "नमस्ते, सब ठीक है? कल मिलते हैं, धन्यवाद।"),
    # Multi-sentence long scam — the dynamic-risk-timeline demo (Risk(t)
    # climbs as the bank claim → threat → OTP ask appear over time).
    "tts_hindi_scam_long.mp3": ("hi",
                                "नमस्ते, मैं आपके बैंक की ओर से बोल रहा हूँ। "
                                "आपका खाता आज शाम को बंद हो जाएगा। "
                                "अगर आप अभी अपना ओटीपी नहीं बताएंगे तो आपका पैसा डूब जाएगा। "
                                "कृपया तुरंत अपना ओटीपी बताइए।"),
}


def main() -> int:
    try:
        from gtts import gTTS
    except ImportError:
        print("gTTS not installed — run: pip install gTTS (one-off tool)")
        return 1

    OUT_DIR.mkdir(exist_ok=True)
    for name, (lang, text) in SCRIPTS.items():
        out = OUT_DIR / name
        gTTS(text=text, lang=lang).save(str(out))
        print(f"  wrote {name}  ({lang}, {len(text)} chars)")
    print("Done — files are TTS-generated; see demo_data/README.md for labelling.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
