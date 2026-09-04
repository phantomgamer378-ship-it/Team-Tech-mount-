# 🛡️ Voice Clone Shield — PROTOTYPE

> **PROTOTYPE for an internal Smart India Hackathon round — not a production
> call-security system.** It analyses *recorded / uploaded / microphone* audio
> only; there is no SIM/cellular call interception. Whenever a heavyweight
> model isn't loaded, services return **clearly-labelled demo-mode output**
> ("DEMO MODE — not real inference") instead of crashing (§20).

## Problem

AI voice cloning makes impersonation scams (fake bank officials, police,
relatives) far more convincing. This prototype proves the intelligence
pipeline end-to-end:

```
Audio → Voice/Deepfake Detection → Hindi/Marathi ASR → Scam Analysis
      → Risk Fusion (0–100) → Liveness Challenge (HIGH only)
      → Threat Warning → Dashboard
```

## Current status — Phase 1 (backend skeleton) ✅

- [x] FastAPI app + permissive CORS for local dev + `/api/health`
- [x] `.env` configuration incl. `DEMO_MODE`
- [x] §13 response-contract Pydantic schemas
- [x] Placeholder services: VoiceDetector, ASRService, ScamDetector,
      RiskEngine, LivenessService (each returns demo-mode mock output)
- [x] requirements.txt, .env.example, smoke tests
- [x] Phase 2: audio preprocessing (16 kHz mono pipeline + 1 s chunker)
- [x] Phase 3: real AASIST-L voice/deepfake detector (loaded at startup, real
      inference on CPU ~250 ms/clip, demo-mode fallback intact)
- [ ] Phase 4–5: IndicConformer ASR + rule-based scam detector
- [ ] Phase 6–9: risk fusion endpoint, liveness API, full wiring, WebSocket
- [ ] Phase 10: Flutter dashboard

## Project structure

```
voice-clone-shield/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entrypoint
│   │   ├── config.py            # .env-driven settings
│   │   ├── api/                 # routers (health now; analyze in Phase 8)
│   │   ├── services/            # VoiceDetector, ASRService, ScamDetector,
│   │   │                        #   LivenessService, AudioProcessor
│   │   ├── risk/                # RiskEngine (weighted fusion, §8)
│   │   ├── models/schemas.py    # §13 API contract
│   │   ├── database/            # SQLite stub (later phase, §17)
│   │   └── utils/               # logging setup
│   ├── tests/                   # smoke tests
│   ├── requirements.txt
│   └── .env.example
├── frontend/flutter_app/        # Phase 10
├── demo_data/                   # Phase 13 test audio/messages
├── scripts/                     # helper scripts
└── docs/                        # architecture/setup/demo docs
```

## Backend setup (macOS, Python 3.11)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # demo mode is ON by default
```

## Run the server

```bash
# From backend/ with the venv active.
# 0.0.0.0 matters: a phone/emulator on the same Wi-Fi must be able to
# reach the API (§12). Android emulator reaches the host at 10.0.2.2.
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Verify it works

```bash
curl http://127.0.0.1:8000/api/health
```

Expected (Phase 1, demo mode on):

```json
{
  "status": "ok",
  "app": "Voice Clone Shield",
  "version": "0.1.0",
  "demo_mode": true,
  "services": {
    "voice_detector": "demo_mode",
    "asr_service": "demo_mode",
    "scam_detector": "stateless",
    "risk_engine": "stateless",
    "liveness_service": "stateless"
  }
}
```

From a phone on the same Wi-Fi (Flutter connectivity check, §12):
`curl http://<your-mac-LAN-IP>:8000/api/health` — find the IP with
`ipconfig getifaddr en0`.

Run the tests: `python -m pytest -v` (from `backend/`).

### Live demo card (works today — §3)

```bash
# from the repo root, with the venv active
python scripts/demo_pipeline.py demo_data/test_babble_16k.wav --lang hi
python scripts/demo_pipeline.py path/to/team_recording.wav --lang mr
```

Prints the full demo card: real AASIST-L deepfake score, demo-mode
transcript/indicators (clearly labelled, §20), the real §8 risk-fusion
formula, a liveness challenge on HIGH risk, and the security warning.
Every signal is tagged REAL vs DEMO-MODE so judges see the honest picture.

### Phase 2 quick check (audio pipeline)

```bash
# from the repo root, with the venv active
python scripts/gen_test_audio.py                             # writes synthetic WAVs to demo_data/
python scripts/check_audio.py demo_data/test_tone_44k_stereo.wav
python scripts/check_audio.py demo_data/test_too_short.wav   # shows the §20 fallback, no crash
```

Expected for the 44.1 kHz stereo file: resampled to 16 kHz mono, ~32000
samples, peak ≈ 1.0 after normalization, 2 one-second chunks. `.m4a` is
deliberately unsupported (needs ffmpeg) — record/convert to WAV.

## Honesty notes (judges will ask — §26)

- **Deepfake model (in use since Phase 3):** pretrained **AASIST-L**
  (anti-spoofing, MIT-licensed, architecture from the official
  [clovaai/aasist](https://github.com/clovaai/aasist) repo; checkpoint from
  `SpeechAntiSpoofingBenchmarks/AASIST-L` on Hugging Face — auto-downloaded,
  or pre-fetch it with `python scripts/download_voice_model.py`).
  Published context for this model family: **~1% EER on ASVspoof2019-LA**
  (its own training benchmark), **12–17% EER on ASVspoof2021**, and **40%+ on
  "in the wild" audio**. It has **never been evaluated on Hindi/Marathi
  speech** — the UI and every analysis response carry this disclaimer.
  Score semantics: `voice_risk = 1 − P(bonafide)`; the 0.5 decision threshold
  is an **uncalibrated prototype cut**.
- **Risk fusion weights (0.40/0.40/0.20):** transparent placeholders, not
  scientifically validated.
- **Liveness (§9):** naive challenge-response; it does **not** defeat
  sophisticated voice cloning.
- Full PROTOTYPE-vs-FUTURE-PRODUCT table and roadmap land in this README in
  Phase 14 (§27).
