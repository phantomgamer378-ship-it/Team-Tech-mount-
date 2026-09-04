# 🛡️ Voice Clone Shield — Implementation Plan (`future.md`)

> Single source of truth for **what's built, what's next, and where the real
> product goes**. Update this file after every phase (mark ✅, add evidence).
>
> Ground rule that overrides everything else (§28): *a working end-to-end
> pipeline beats perfect individual components. Demo reliability beats
> production complexity. Clear architecture beats excessive features.*
>
> Second ground rule (§5/§20/§26): never claim prototype components are
> production-ready or scientifically validated. Every mock is labelled, every
> limitation is stated out loud to judges before they ask.

---

## 1. Status snapshot — where we are today

Updated: 2026-09-04 (after Phase 3 + terminal demo runner)

| # | Phase (§25) | Status | Evidence / notes |
|---|---|---|---|
| 1 | Repo, env, FastAPI skeleton, health check | ✅ DONE | `/api/health` live on `0.0.0.0:8000`; CORS permissive (prototype-only); `.env` config incl. `DEMO_MODE`; §13 schemas |
| 2 | Audio preprocessing (§14) | ✅ DONE | `audio_processor.py`: load→validate→mono→16 kHz→normalize→chunk; all failure modes return §13 fallback, never crash |
| 3 | Voice detector — real AASIST-L (§5) | ✅ DONE | Official architecture (MIT) ported to `app/ml/aasist.py`; checkpoint auto-downloads (426 KB, HF `SpeechAntiSpoofingBenchmarks/AASIST-L`, verified byte-identical size to official clovaai file); loads once at startup w/ warm-up; ~250 ms/clip CPU; deterministic; `voice_risk = 1 − P(bonafide)` per official convention |
| 6 | Risk fusion engine (§8) | 🟡 EARLY | `risk_engine.py` implements the real 0.40/0.40/0.20 formula + LOW/MEDIUM/HIGH bands; used by demo runner. **Left for Phase 6 pass:** dedicated unit tests + calibration hook |
| 7 | Liveness service (§9) | 🟡 EARLY | Challenge generation + naive verify implemented (in-memory). **Left:** expiry, endpoint wiring (Phase 8) |
| — | Terminal demo runner (§3 card) | ✅ DONE (pulled forward) | `scripts/demo_pipeline.py` prints the full demo card with honest REAL vs DEMO-MODE tags; works on any WAV; `--lang hi/mr` |
| — | Tests | ✅ 20 passing | `python -m pytest -v` from `backend/` |

**What is REAL today:** preprocessing, AASIST-L deepfake scoring, risk-fusion
formula, liveness challenge, graceful-fallback behaviour everywhere.
**What is DEMO-MODE today:** transcript (mock §3 script, hi/mr), scam
indicators/score (mock), context risk (hard 0.0, no signal source yet).

## 2. Remaining phases (the build order)

Each phase: generate → run → verify → fix → explain → only then move on (§25).
Time-boxes assume one machine + the existing venv.

### Phase 4 — Hindi/Marathi ASR, real (§6) — 2–3 hrs — **biggest download, start early**
- [ ] Add `transformers` dep; implement IndicConformer
      (`ai4bharat/indic-conformer-600m-multilingual`, `trust_remote_code=True`)
      inside the existing `ASRService` — interface already matches, no caller changes.
- [ ] Implement faster-whisper as `ASR_BACKEND=faster_whisper` fallback behind
      the same interface (the §24 10-minute escape hatch).
- [ ] Pre-cache both models the night before any demo (`scripts/download_asr_model.py`).
- [ ] Accuracy disclaimer everywhere: code-mixed Hinglish/Marathi-English WILL
      degrade; not fine-tuned on Indian speech.
- **Done when:** a team-recorded Hindi WAV returns the correct transcript via
  `scripts/demo_pipeline.py` (tag flips from DEMO MODE to REAL), and a forced
  backend switch works by changing one env var.

### Phase 5 — Scam detector, real rules (§7) — 1–2 hrs
- [ ] Rule/keyword engine in `scam_detector.py`: OTP/PIN, bank/KYC
      impersonation, account-blocking threat, urgency, police/authority
      impersonation, money transfer, investment/job/parcel, family-emergency,
      secrecy, credential requests — Hindi + Marathi + common English/code-mixed.
- [ ] Score = transparent function of matched indicators (weights documented,
      not validated). Keep mock path for empty transcript.
- **Done when:** the §3 scripts score HIGH with correct indicators, and a
  casual-conversation transcript scores LOW. Unit tests for both.

### Phase 6 — Risk fusion hardening (§8) — 1 hr
- [ ] Unit tests for bands (29/30, 69/70 boundaries), clamping, missing signals.
- [ ] Document + expose the weights; add a `calibrate()` no-op hook where a
      trained classifier plugs in later (roadmap F).
- **Done when:** `pytest` covers `risk_engine.fuse` comprehensively.

### Phase 7 — Liveness hardening (§9) — 1 hr
- [ ] Challenge expiry (e.g. 60 s), single-use, per-session store cleanup.
- [ ] Keep the honesty note: text-match does NOT defeat cloning.
- **Done when:** expired/replayed challenges return FAILED/SUSPICIOUS.

### Phase 8 — FastAPI integration, the real endpoints (§12/§13) — 1–2 hrs — **demo-critical**
- [ ] `POST /api/analyze/audio` (multipart upload → full §13 `AnalysisResponse`)
- [ ] `POST /api/liveness/start` + `POST /api/liveness/verify`
- [ ] `GET /api/history` (SQLite: sessions, analysis_results, threat_events — §17)
- [ ] Upload validation: type/size (reuse `MAX_UPLOAD_MB`); no raw-audio
      retention beyond the request (§23).
- **Done when:** `curl -F audio=@demo_data/x.wav http://<ip>:8000/api/analyze/audio`
  returns the §13 JSON from a **second device on LAN**.

### Phase 9 — WebSocket simulated real-time (§15) — 1–2 hrs
- [ ] `WS /ws/session/{id}`: client streams 1 s chunks (from `AudioProcessor.chunk`),
      server sends progressive status; final card on last chunk.
- [ ] No true streaming inference — simulation only, labelled as such.
- **Done when:** a browser/Python WS client sees risk build up chunk-by-chunk.

### Phase 10 — Flutter dashboard (§16) — 3–4 hrs, TIMEBOXED
- [ ] Screens: Home/Dashboard, Call Analysis (primary), Liveness, Message/URL
      Scanner, Threat History. Dark cybersecurity aesthetic, function > polish.
- [ ] Calls `http://<LAN-IP>:8000` (never `localhost`; Android emulator = `10.0.2.2`).
- [ ] "Prototype Analysis" label whenever `fallback_used`/mock models are active.
- **Done when:** full §3 demo runs from a phone against the laptop server.

### Phase 11 — Message scanner (§10) — 1 hr
- [ ] `POST /api/analyze/message`: same scam rules on text; §13-style response
      (`risk_score`, `risk_level`, `category`, `indicators`).
- **Done when:** `scam_hindi.txt` → HIGH, `normal_message.txt` → LOW.

### Phase 12 — URL checker (§10) — 1 hr
- [ ] `POST /api/analyze/url`: structure checks — IP-based host, punycode/
      misleading domains, suspicious keywords (login/verify/otp-bank), long
      random subdomains. Heuristics only, no live fetching (prototype).
- **Done when:** obviously bad URL → HIGH with reasons; google.com → LOW.

### Phase 13 — Demo data + honest evaluation (§21/§22) — 1–2 hrs + recording session
- [ ] Record: `real_hindi.wav`, `real_marathi.wav`, `normal_conversation.wav`
      (2–3 team members, phone, quiet room).
- [ ] Generate fakes: gTTS (simplest) or AI4Bharat TTS → `fake_hindi.wav`,
      `fake_marathi.wav`, `hindi_scam.wav`, `marathi_scam.wav`.
- [ ] Text set: `scam_hindi.txt`, `scam_marathi.txt`, `normal_message.txt`.
- [ ] Evaluation sheet: per sample — prediction, score, expected label. Report
      only measured numbers; note EER only if actually computed.
- **Done when:** the LOW-risk control demo exists (judges WILL ask) and the
  sheet has real rows in it.

### Phase 14 — Polish + README + Q&A (§26/§27) — 1–2 hrs
- [ ] Final README: PROTOTYPE vs FUTURE PRODUCT columns, model info, setup,
      demo flow, API docs, limitations, this roadmap.
- [ ] Rehearse the §26 answers (below) out loud, twice.
- [ ] Night-before checklist: models cached ✓, server boots offline ✓,
      backup audio files ✓, second-device curl ✓.

---

## 3. Scope guardrails — what we are NOT building (§2)

SIM/cellular interception · carrier telephony · production infra · "perfect"
detection · models trained from scratch · enterprise auth · Kubernetes ·
microservices. If a task drifts toward any of these, stop.

## 4. FUTURE PRODUCT roadmap (documented, not built — §27)

| Phase | What | Why it matters |
|---|---|---|
| A | Evaluate deepfake detector on Hindi/Marathi test set | Turns our disclaimer into a measured number |
| B | Collect Indian-language real/fake speech dataset | Training/evaluation data we currently lack |
| C | Fine-tune + calibrate anti-spoofing (thresholds, EER) | Fixes the uncalibrated 0.5 cut |
| D | Improve Hindi/Marathi/code-mixed ASR | Real Hinglish calls are the norm |
| E | Train a dedicated scam classifier (replaces keyword rules) | Rules miss paraphrases |
| F | Replace weighted fusion with calibrated model | Weights 0.40/0.40/0.20 are placeholders |
| G | Robust liveness / speaker verification | Current challenge is text-match only |
| H | WebRTC ingestion | Real-time mic/browser calls |
| I | SIP/telephony integration | Actual phone-call protection (8 kHz codecs!) |
| J | Cloud deployment, scaling | Beyond one laptop |
| K | Monitoring, model versioning, drift detection | Keep it honest in production |
| L | Security/privacy/compliance hardening | Encryption at rest, consent, retention, DPDP |

## 5. PROTOTYPE vs FUTURE PRODUCT (§27)

| Capability | PROTOTYPE (today) | FUTURE PRODUCT |
|---|---|---|
| Audio in | recorded / uploaded / mic file | live WebRTC/SIP call stream |
| Deepfake detection | pretrained AASIST-L, unvalidated on hi/mr | fine-tuned + calibrated (A–C) |
| ASR | IndicConformer/faster-whisper off-the-shelf | fine-tuned for code-mixed speech (D) |
| Scam detection | keyword rules (E replaces) | trained classifier |
| Fusion | fixed weights 0.4/0.4/0.2 | calibrated model (F) |
| Liveness | text-match challenge | speaker verification (G) |
| Real-time | simulated 1 s chunks over WS | streaming inference |
| Infra | one laptop, SQLite, permissive CORS | cloud, Postgres, locked CORS/auth (J–L) |

## 6. Risk register (§24, updated)

| Risk | Likelihood | Impact | Mitigation | Status |
|---|---|---|---|---|
| IndicConformer install eats hours | Med-High | High | transformers route + faster-whisper fallback behind same interface | Open — Phase 4 |
| Model download fails at venue | Medium | High | cache night before, ship on disk; `download_voice_model.py` | **AASIST mitigated**; ASR pending |
| No GPU | Medium | Med | CPU-only everywhere, warm-up at startup | Verified: ~250 ms/clip CPU |
| Flutter can't reach FastAPI | High if untested | High | curl from second device; LAN IP / 10.0.2.2, never localhost | Open — test in Phase 10 |
| No real scam audio | High | Med | §21 recordings + TTS, labelled synthetic | Open — Phase 13 |
| Model garbage/timeout mid-demo | Medium | High | DEMO_MODE fallback = launch-blocking requirement, not nice-to-have | Built + tested |
| Flutter polish eats pipeline time | Medium | High | Phase 10 timeboxed 3–4 hrs; function first | Watch |
| Judges ask about real telephony | High | Low if prepared | §26 answers rehearsed | Ready |

## 7. Judge Q&A — rehearse these (§26)

- **"Does this work on a real phone call?"** → "Today it proves the intelligence
  pipeline on recorded/uploaded/mic audio; real-time call interception via
  WebRTC/SIP is our next integration phase, not what we're validating today."
- **"How accurate on Hindi/Marathi deepfakes?"** → "The pretrained model is
  benchmarked on English ASVspoof (~1% EER 2019-LA, 12–17% 2021, 40%+ in the
  wild). We have not yet validated it on Indian-language speech — that is
  roadmap phase A, and we label it as such in the UI."
- **"Hinglish/code-mixed?"** → "Accuracy degrades; known limitation, transparent
  about it; fine-tuning is on the roadmap."
- **"What if a model fails mid-demo?"** → "It falls back to clearly-labelled
  demo mode instead of crashing — reliability was a design constraint."
- **"Why should we trust the risk score?"** → "You shouldn't blindly — the
  fusion weights are transparent placeholders (0.4/0.4/0.2); a calibrated
  model replaces them in roadmap phase F."

## 8. Working agreements (§28)

Build incrementally · explain generated code · keep API contracts stable ·
inspect errors before regenerating · never swap frameworks mid-build · state
file + command + expected output for every drop · never present demo-mode
output as real inference.

**Most important:** working end-to-end > perfect components. We already have
the end-to-end card (terminal); every remaining phase makes one more signal
real — the demo can never fall below where it is today.
