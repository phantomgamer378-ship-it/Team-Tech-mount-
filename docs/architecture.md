# 🏗️ Voice Clone Shield — Architecture & Implementation Plan

> **Deliverable for the v3 MASTER BUILD PROMPT "FIRST TASK"** — the 12 design
> items, produced *before* any further implementation, as required.
> **No backend code was changed in this pass.** Implementation resumes only
> after approval (see §12).
>
> Positioning (per the master prompt): Voice Clone Shield is **"an AI-powered
> voice trust and fraud-prevention layer that combines voice authenticity,
> identity consistency, conversation intent, contextual evidence, liveness and
> policy decisions into a dynamic risk score."** The core security question is
> *"Can I trust this interaction?"* — not "is this file AI-generated?".

---

## 0. Where we stand vs this plan (gap analysis)

Work already completed under the earlier plan carries forward — the architecture
below was designed around it, not from scratch.

| v3 Phase | Scope | State today |
|---|---|---|
| 1 | repo + env + FastAPI skeleton | ✅ **done** (app boots on `0.0.0.0:8000`, CORS, `.env`, logging, tests) |
| 2 | schemas + database + health | ✅ **DONE** — `schemas.py` = frozen v3 contract (37 tests green); SQLite 6 tables; `PRIVACY_MODE` on; health reports DB status |
| 3 | audio ingestion + preprocessing | ✅ **done** (validate→mono→16 kHz→normalize→chunk, full fallback discipline, 11 tests) |
| 4 | model adapter interfaces + demo adapters | ✅ **DONE** — `app/demo/` package (DemoVoiceDetector, DemoASRService, DemoScamDetector, DemoSpeakerVerifier): contract-native, deterministic, hint-routed demo scenarios, `USE_DEMO_SERVICES` container switch; real services delegate their fallbacks to the same mocks; liveness fixed-phrase + PASSED state; 52 tests green |
| 5 | ASR adapter | ✅ **DONE** — multi-backend `ASRService`: **faster-whisper 'small'** (working default, not gated, CPU int8, real transcripts + model-provided LID confidence + segment timing) + **IndicConformer implemented, awaiting HF access** (repo is GATED — needs access request + token; one-line `ASR_BACKEND` switch); TTS hi/mr samples validate the path end-to-end; 60 tests green |
| 6 | voice detector adapter | ✅ **done and ahead** — real AASIST-L inference, loaded once at startup, ~250 ms/clip CPU |
| 7 | scam analysis | ✅ **DONE** — real rule engine: 14 concepts, hi/mr/en + ASR spelling-variant normalization (अटीपी→ओटीपी, बन्द→बंद), transparent additive weights (prototype-only), category rules, `[scam_rule]` evidence lines; tested against the ACTUAL faster-whisper transcripts |
| 8 | attack classification | ✅ **DONE** — `attack_types_from_indicators()`: pure multi-label lookup (no model, per master prompt), includes voice-evidence label; unit-tested |
| 9 | risk fusion | ✅ **DONE** — v3 5-signal weights (0.30/0.20/0.30/0.10/0.10, demo-only); signals with no evidence are excluded + weights renormalized (never invented); 4-tier bands LOW<40≤MEDIUM<70≤HIGH<85≤CRITICAL; `fuse_timeline()` per-chunk Risk(t) with evidence persistence (running max, caveats documented); `weights_used` exposed for transparency |
| 10 | policy engine | ✅ **DONE** — pure `decide()`: LOW→CONTINUE, MEDIUM→CAUTION, HIGH→VERIFY_CALLER, CRITICAL→WARN; fail-safe (unknown level → WARN); unit-tested |
| 11 | liveness | ✅ **DONE** — tiered via `liveness_decision()` (NONE<40 / MONITOR 40–69 / CHALLENGE 70–84 / MANDATORY ≥85); fixed prototype phrase; challenge expiry (`LIVENESS_EXPIRY_SECONDS`, late responses → FAILED); states PENDING/PASSED/SUSPICIOUS/FAILED; start/verify endpoints persist outcomes |
| — | **HTTP API wiring** (was v2 Phase 8) | ✅ **DONE** — one orchestrator (`app/pipeline.py`) shared by the terminal card AND `POST /api/analyze/audio`; `POST /api/session`, `GET /api/history`, `GET /api/session/{id}`; uploads validated (type/size), temp audio deleted after analysis (privacy_mode); every response fits the two frozen shapes; verified end-to-end with curl + real models |
| 12 | WebSocket dynamic risk | ❌ not built |
| 13 | Flutter dashboard | ❌ not built |
| 14 | message scanner | ❌ not built |
| 15 | URL checker | ❌ not built |
| 16 | trusted voice memory prototype | ❌ stub planned |
| 17 | testing & integration | 🟡 20 tests pass, but against the old contract |
| 18 | demo polish | 🟡 terminal demo card exists (`scripts/demo_pipeline.py`); needs new contract + 5 scenarios |

**What is REAL today:** preprocessing · AASIST-L deepfake scoring · risk-fusion
formula · liveness challenge · graceful fallback everywhere.
**What is DEMO-MODE today:** transcript (hi/mr script mock) · scam indicators ·
context risk (hard 0.0) · speaker identity (no signal source yet).

---

## 1. Architecture overview

One flow, five parallel evidence branches, one fusion, one policy layer:

```
                AUDIO / CALL (upload · mic · simulated WS chunks)
                                  |
                                  v
                        AUDIO INGESTION  (POST /api/session)
                                  |
                                  v
                       AUDIO PREPROCESSING  (§3 done)
                    validate → mono → 16 kHz → normalize
                                  |
        +------------------+------+----------+------------------+
        |                  |                 |                  |
        v                  v                 v                  v
  VOICE TRUST        ASR BRANCH       SCAM INTENT         CONTEXT
  ENGINE                   |             ENGINE            SIGNALS
  (prototype)              v                 |             (stub, 0.0)
  AASIST anti-spoof   LANGUAGE ID            |
  + Whisper branch    (hi/mr/code-mix)       v
  (features stub)          |          intent evidence
        |                  v                 |
        |          HINDI/MARATHI/CODE-MIXED  |
        |               TEXT                 |
        |                  v                 |
        |          SCAM INTENT ENGINE --------+
        |                  |
        +--------+---------+------------------+
                 |
                 v
        SPEAKER / IDENTITY LAYER  (prototype: stub / demo profile only)
                 |
                 v
        EVIDENCE NORMALIZATION  (one schema, source-tagged)
                 |
                 v
        DYNAMIC RISK FUSION   risk(t) per chunk  +  final score
                 |
                 v
            POLICY ENGINE  (pure: tier → action)
                 |
          +------+------+
          |             |
          v             v
      LOW / MEDIUM    HIGH / CRITICAL
          |             |
          v             v
       CONTINUE    ADAPTIVE LIVENESS (monitor → challenge)
                        |
                        v
                 FINAL RISK UPDATE
                        |
                        v
              WARN / VERIFY / PREVENT (recommendation)
                        |
                        v
              DASHBOARD / API / LOG (SQLite, no raw audio)
```

**Why multiple branches (the conceptual distinction judges must hear):**
"Is it fake?" (deepfake detection) ≠ "Who is it?" (identity) ≠ "What are they
doing?" (intent). One classifier cannot answer all three; the fusion layer
combines independent evidence.

### USP → module mapping (architecture MUST support all 10)

| # | USP | Supported by |
|---|---|---|
| 1 | Multi-Layer Voice Trust Engine | `voice_detector` (AASIST) + `whisper_features` (stub branch) + `evidence_normalizer` |
| 2 | Dynamic Risk Score | `risk_engine` per-chunk `risk_timeline` + WebSocket push |
| 3 | Bharat Voice Shield (hi/mr/code-mixed) | `asr_service` (IndicConformer primary, Whisper-class fallback) + disclaimers |
| 4 | Scam Intent Detection | `scam_detector` rule engine (concepts, not just keywords) |
| 5 | Attack-Type Classification | `attack_classifier` (pure indicator→type lookup) |
| 6 | Adaptive Liveness | `policy_engine` tiers + `liveness_service` states |
| 7 | Trusted Voice Memory | `speaker_verifier` stub + `voice_profiles` table + `/api/voice-profile/enroll` flow |
| 8 | Privacy-First Voice Security | `privacy_mode=true` default; no raw-audio persistence; minimal metadata |
| 9 | Explainable Evidence | `evidence_normalizer` + `explanation[]` with `voice / scam_rule / fused / identity` source tags |
| 10 | Whisper-assisted layer | `whisper_features` stub + swappable ASR — **Whisper is never the deepfake detector** |

---

## 2. Component diagram (module level)

```
 backend/app/
   main.py ──────────────── lifespan: ServiceContainer.load_all() once
     │
     ├── api/ (routes only — no ML code)
     │     session.py  audio.py  messages.py  urls.py
     │     liveness.py  voice_profiles.py  websocket.py
     │
     ├── services/  (the intelligence, behind interfaces)
     │     audio_processor.py ──┐
     │     voice_detector.py ───┤  AASISTVoiceDetector (real today)
     │     whisper_features.py ─┤  stub branch (future research hook)
     │     asr_service.py ──────┤  IndicConformer → faster-whisper fallback
     │     scam_detector.py ────┤  RuleScamDetector
     │     attack_classifier.py ┤  PURE indicator→attack-type lookup
     │     speaker_verifier.py ─┤  stub (null risk unless demo profile)
     │     liveness_service.py ─┘  tiered challenge, 4 states
     │
     ├── risk/
     │     evidence_normalizer.py   unified evidence record + source tags
     │     risk_engine.py           5-signal weighted fusion + risk(t)
     │     policy_engine.py         pure tier→action function
     │
     ├── models/schemas.py          ★ frozen contract (single source of truth)
     ├── database/                  SQLite; metadata only, no raw audio
     ├── demo/                      Demo* mocks of every service (safety net)
     └── utils/                     logging, validation
```

Data never bypasses the interfaces: routes call services, services return
plain dicts matching `schemas.py`, the normalizer tags provenance, the engine
fuses, policy decides.

---

## 3. Prototype vs production

| Capability | PROTOTYPE (now) | REAL PRODUCT (future) |
|---|---|---|
| Audio source | uploaded WAV / mic recording / simulated WS chunks | live telephony, VoIP, enterprise audio ingestion |
| Preprocessing | batch, 16 kHz mono, 1 s chunks | streaming gateway, VAD, low-latency |
| Anti-spoofing | pretrained AASIST-L baseline, **not yet evaluated on Indian-language speech** | regional fine-tuned/calibrated model, multi-generator robust |
| Whisper | ASR swap-in + features stub | representation branch fused into spoof classifier |
| ASR | IndicConformer / faster-whisper off-the-shelf | fine-tuned Hindi/Marathi/code-mixed/telephony |
| Scam analysis | deterministic rules + structured evidence | trained intent classifier, LLM assist |
| Attack types | pure lookup from indicators | multi-label model |
| Identity | conceptual flow + stub, demo profile only | speaker embeddings, cross-session trusted memory |
| Risk | transparent weighted fusion, prototype weights | calibrated/temporal fusion model |
| Liveness | fixed-phrase challenge, text-match hook | random challenges, replay resistance, speaker verification |
| Policy | static tier→action map | configurable enterprise/bank/government rules |
| Real time | simulated (chunks over WS) | WebRTC/SIP media gateway, streaming workers |
| Data/DB | SQLite, no raw audio retained | Postgres, encrypted feature store, retention policies |
| MLOps | none (structure reserved) | registry, monitoring, drift, retraining |
| Scale | one laptop | API layer + inference workers + cache |

Honest phrasing rule (all docs/UI): *"pretrained baseline, not yet evaluated on
Indian-language speech"* — never "validated for Hindi/Marathi", never "100%
detection", never "voice match proves identity".

---

## 4. Module responsibility table

| Module | Responsibility | Key interface | Demo fallback | Status |
|---|---|---|---|---|
| `services/audio_processor.py` | validate→mono→16 kHz→normalize→1 s chunks | `preprocess(path) -> dict` | n/a (pure) | ✅ done |
| `services/voice_detector.py` | spoof probability from signal only | `predict(waveform) -> dict` | `DemoVoiceDetector` shape | ✅ real (AASIST-L) |
| `services/whisper_features.py` | optional Whisper encoder representations | `extract(waveform) -> dict or None` | returns `{"available": false, ...}` | ⬜ stub (Phase 4) |
| `services/asr_service.py` | language + transcript + segments | `transcribe(waveform) -> dict` | `DemoASRService` (§3 scripts) | 🟡 mock → Phase 5 real |
| `services/scam_detector.py` | intent concepts → indicators + score | `analyze(transcript) -> dict` | `DemoScamDetector` | 🟡 mock → Phase 7 rules |
| `services/attack_classifier.py` | indicator set → attack-type labels | `classify(indicators, voice) -> [str]` | pure function — same | ⬜ Phase 8 (small) |
| `services/speaker_verifier.py` | identity-consistency risk | `compare(waveform, profile) -> dict` | `DemoSpeakerVerifier` (null) | ⬜ stub (Phase 16) |
| `services/liveness_service.py` | tiered challenge lifecycle | `start/verify(session) -> dict` | n/a (no model) | 🟡 upgrade Phase 11 |
| `risk/evidence_normalizer.py` | unify signals into one schema, tag source | `normalize(signal, score, source) -> dict` | n/a | ⬜ Phase 4/9 |
| `risk/risk_engine.py` | weighted fusion + `risk_timeline` | `fuse(signals) / fuse_chunk(...)` | n/a | 🟡 upgrade Phase 9 |
| `risk/policy_engine.py` | tier → policy action (pure) | `decide(level, liveness) -> str` | n/a | ⬜ Phase 10 |
| `services/privacy_service.py` | enforce privacy_mode, strip sensitive logs | helpers | n/a | ⬜ small, Phase 2/17 |
| `demo/*` | standalone mocks matching contract exactly | mirrors each service | — | ⬜ Phase 4 (**first**) |
| `models/schemas.py` | the frozen contract | Pydantic models | — | 🟡 rewrite Phase 2 |
| `api/*` | routing only | — | — | 🟡 expand Phases 2–16 |
| `database/` | SQLite sessions/results/events/voice_profiles | — | — | ⬜ Phase 2 |

**Hard rule for all adapters:** models load once at startup (`lifespan`), never
per call; every real call is wrapped — on any failure return the demo/fallback
shape so the API layer never sees an exception.

---

## 5. API contract (the frozen shapes)

### Canonical success shape — `/api/analyze/audio`

```json
{
  "session_id": "demo-001",
  "status": "complete",
  "audio": { "duration": 23.4, "language": "mr" },
  "voice_trust": {
    "spoof_risk": 0.91,
    "speaker_mismatch_risk": 0.72,
    "overall_voice_risk": 0.84,
    "status": "SUSPICIOUS"
  },
  "asr": { "language": "mr", "transcript": "...", "segments": [] },
  "scam_analysis": {
    "risk": 0.88,
    "category": "Bank/KYC Fraud",
    "indicators": ["Urgency", "OTP request"]
  },
  "attack_types": ["AI Voice Impersonation", "Bank Fraud"],
  "risk": { "score": 91, "level": "HIGH" },
  "liveness": { "required": true, "status": "PENDING" },
  "explanation": [
    "[voice] Synthetic voice evidence detected",
    "[scam_rule] Urgent financial request detected",
    "[scam_rule] OTP request detected",
    "[fused] Combined risk crossed HIGH threshold"
  ],
  "recommendation": "Do not share OTP or transfer money."
}
```

Fallback shape (unchanged from current code — every failure uses it):
```json
{ "status": "partial", "error": "Voice model unavailable", "fallback_used": true }
```

### Endpoints

| Method | Path | Notes |
|---|---|---|
| POST | `/api/session` | create session, returns `session_id` |
| POST | `/api/analyze/audio` | upload → full canonical response (+ `risk_timeline` array) |
| POST | `/api/analyze/message` | text → scam analysis + attack types |
| POST | `/api/analyze/url` | heuristics only, no live fetching |
| POST | `/api/liveness/start` / `/api/liveness/verify` | tier-gated |
| POST | `/api/voice-profile/enroll` | conceptual flow; metadata only (no embedding model yet) |
| GET | `/api/history`, `/api/session/{id}` | from SQLite |
| GET | `/api/health` | per-service loaded/demo status |
| WS | `/ws/session/{session_id}` | one message per chunk: `{t, voice_risk, scam_risk, risk_score, level}` |

### ⚠️ Contract deltas vs the code that exists today (Phase 2 must apply these)

1. `voice_analysis` → **`voice_trust`** with `spoof_risk` / `speaker_mismatch_risk` / `overall_voice_risk` / `status`.
2. Top-level `language` + `transcript` move into an **`asr`** object (`segments`, `confidence` only if the model actually provides it).
3. **New fields:** `status: "complete"`, `audio {duration, language}`, `attack_types[]`, `explanation[]` (source-tagged), `recommendation`.
4. **Risk levels become 4 tiers.** Proposed prototype bands (align with the liveness tiers in the master prompt): **LOW 0–39 · MEDIUM 40–69 · HIGH 70–84 · CRITICAL 85–100.**
5. **Fusion weights change** to `0.30·voice + 0.20·identity + 0.30·scam + 0.10·context + 0.10·liveness` (demo weights only, never claim calibration). Identity/liveness default to neutral (0.0/0.5-equivalent) until their signals exist — documented, not hidden.
6. **Liveness states become** `PENDING / PASSED / SUSPICIOUS / FAILED` (currently `LIVE/...`), and the **challenge phrase becomes FIXED** ("Blue Tiger 47") — the current random-phrase generator gets simplified; randomization is future work.
7. Scam detector internally reports `intent_score`; the API exposes it as `scam_analysis.risk`.
8. `risk_timeline[]` added to the audio response (per-chunk `{t, risk_score, level}`) — this is the dynamic-risk demo moment.

---

## 6. Folder structure (target vs today)

```
voice-clone-shield/
├── backend/app/            main.py ✅ · config.py ✅
│   ├── api/                health ✅ · session ⬜ · audio ⬜ · messages ⬜ · urls ⬜
│   │                       liveness ⬜ · voice_profiles ⬜ · websocket ⬜
│   ├── services/           audio_processor ✅ · voice_detector ✅ · asr_service 🟡
│   │                       scam_detector 🟡 · liveness_service 🟡
│   │                       whisper_features ⬜ · attack_classifier ⬜
│   │                       speaker_verifier ⬜ · privacy_service ⬜
│   ├── risk/               risk_engine 🟡 · evidence_normalizer ⬜ · policy_engine ⬜
│   ├── models/schemas.py   🟡 (old contract)
│   ├── database/           ⬜ (stub today)
│   ├── demo/               ⬜ (mocks — Phase 4, FIRST)
│   ├── ml/aasist.py        ✅ (official architecture, provenance header)
│   └── utils/              ✅ logging
├── backend/tests/          ✅ 20 tests (old contract) → extend Phase 17
├── frontend/flutter_app/   ⬜ Phase 13
├── demo_data/              🟡 synthetic WAVs; §21 recordings Phase 13-time
├── data/  models/  training/  evaluation/   ⬜ reserved scaffolds (no bulk downloads)
├── docs/                   architecture.md ✅ (this file) · prototype_scope ·
│                           future_product · ml_roadmap · mlops_roadmap ·
│                           privacy · demo_script  ⬜ (Phase 18)
├── scripts/                ✅ gen_test_audio · check_audio · demo_pipeline ·
│                           download_voice_model
├── future.md               ✅ living status (phase banner updated)
└── README.md               ✅
```

`data/`, `models/`, `training/`, `evaluation/` get README-only scaffolds — the
future-training-ready structure without pretending we train anything now.

---

## 7. Data flow — one `POST /api/analyze/audio` request

1. **Session** — client posts audio (multipart) with/without `session_id`; session row created.
2. **Privacy gate** — `privacy_mode=true` (default): audio lives in memory/temp only; SQLite receives metadata + scores + evidence, never audio. Raw-audio logging: never.
3. **Preprocess** (✅ built) — validate (type/size/duration) → mono → 16 kHz → peak-normalize → full waveform + ~1 s chunks.
4. **Voice branch** — AASIST-L on the full clip (official ~4 s window, zero-padded/truncated) → `spoof_risk`; per-chunk scores for the timeline (documented caveat: sub-4 s windows are noisier — prototype-grade, labelled).
5. **ASR branch** — IndicConformer (Phase 5; today: demo script transcript) → `language`, `transcript`, `segments`.
6. **Scam branch** — rule engine over transcript (+ segments) → indicators, `intent_score`, `category`.
7. **Attack classification** — pure lookup over indicators + voice evidence → `attack_types[]` (e.g. OTP+bank → "Bank/KYC Fraud", family+money+urgency → "Family Emergency Scam", high spoof risk → "AI Voice Impersonation").
8. **Identity** — `speaker_verifier` stub: `speaker_mismatch_risk = null` unless a demo voice profile exists; **never claimed to prove identity**.
9. **Evidence normalization** — every signal becomes `{"signal", "score", "direction", "source", "timestamp", "confidence", "metadata"}`; explanation strings carry source tags (`[voice]`, `[scam_rule]`, `[fused]`, `[identity]`).
10. **Risk fusion** — final = `0.30·voice + 0.20·identity + 0.30·scam + 0.10·context + 0.10·liveness` (prototype weights); `risk_timeline[]` = the same fusion per chunk (neutral identity/context/liveness per chunk until those signals exist). Dynamic example from the master prompt (12 → 31 → 57 → 82 → 94) is the demo target.
11. **Policy** — pure `decide(level)`: LOW→CONTINUE · MEDIUM→CAUTION · HIGH→VERIFY_CALLER · CRITICAL→WARN.
12. **Adaptive liveness** — risk < 40: none · 40–69: monitor · 70–84: challenge offered · ≥ 85: mandatory. States: PENDING → PASSED / SUSPICIOUS / FAILED.
13. **Respond + persist** — canonical JSON; `analysis_results` + `threat_events` rows (metadata only). WS variant pushes `{t, risk_score, level}` per chunk instead.

Demo scenarios this flow must serve (deterministic, §DEMO): ① normal call → LOW/CONTINUE · ② Hindi TTS scam → HIGH · ③ Marathi scam (the "आई, मी राहुल बोलतोय…" family-emergency example) → HIGH + liveness · ④ code-mixed scam · ⑤ risk climbing live over WS.

---

## 8. Model adapter strategy

| Interface | Prototype impl (today) | Demo impl | Future impl |
|---|---|---|---|
| `VoiceDetector` | **AASISTVoiceDetector** ✅ real | `DemoVoiceDetector` | `FutureRegionalVoiceDetector` (fine-tuned on IndicSynth-style data, calibrated) |
| `WhisperFeatureExtractor` | stub (returns unavailable) | same | encoder representations fused into spoof research |
| `ASRService` | 🟡 DemoASRService → **IndicConformer** (Phase 5), faster-whisper fallback | DemoASRService | fine-tuned Indic ASR |
| `ScamDetector` | 🟡 → **RuleScamDetector** (Phase 7) | DemoScamDetector | TF-IDF baseline → transformer → calibrated |
| `AttackClassifier` | pure indicator lookup (Phase 8) — **not a model, by design** | same | optional multi-label classifier |
| `SpeakerVerifier` | stub → null risk (Phase 16 conceptual flow) | DemoSpeakerVerifier | embedding model + threshold calibration |
| `LivenessService` | fixed phrase + hook | same | random challenges, anti-replay, speaker verification |
| `RiskEngine` | weighted 5-signal + timeline | same | calibrated/temporal model |
| `PolicyEngine` | pure tier→action | same | configurable external policy |

Rules: one abstract shape per interface · swap via config/env, one-line change ·
models loaded once at startup · **every real call wrapped with a demo fallback
returning the exact same JSON shape** — a model failure is never an error for
the API layer or UI. The `demo/` package is built FIRST (Phase 4) as the team's
safety net, and mocks are always labelled "Prototype / Demo Analysis".

---

## 9. Testing strategy

| Layer | Tests | Status |
|---|---|---|
| Unit — audio validation | missing/corrupt/short/oversized/unsupported → fallback shape | ✅ 11 tests |
| Unit — voice detector | contract, determinism, padding, orientation sanity, fallback | ✅ 7 tests |
| Unit — schemas | canonical shape validates; fallback shape validates | ⬜ Phase 2 (with rewrite) |
| Unit — scam rules | §3 scripts → HIGH + indicators; casual → LOW; per-concept cases | ⬜ Phase 7 |
| Unit — attack classifier | OTP+bank→Bank/KYC; family+money→Family Emergency; spoof→AI Voice Impersonation | ⬜ Phase 8 |
| Unit — risk engine | band boundaries (39/40, 69/70, 84/85), weights, clamping, timeline monotonicity of length | 🟡 upgrade Phase 9 |
| Unit — policy engine | every tier → exact action string | ⬜ Phase 10 |
| Unit — liveness | state transitions PENDING→PASSED/SUSPICIOUS/FAILED, tier gating | ⬜ Phase 11 |
| Unit — URL checker | bad structures → HIGH+reasons; benign → LOW | ⬜ Phase 15 |
| Integration | audio → voice → ASR → scam → attack → evidence → risk → policy, **mock path and real path**, demo-fallback path | ⬜ Phase 17 |
| Fixtures | tiny generated WAVs (existing pattern), scam/normal text files | 🟡 |

Integration test explicitly covers the demo-fallback path — that's a feature
under test, not an accident.

---

## 10. Future ML training plan (documented, NOT implemented)

**Voice anti-spoofing:** ① pretrained baseline (done) → ② evaluate on Hindi/Marathi (first real deliverable post-SIH) → ③ build Indian-language real/fake dataset (IndicSynth candidate — license/research-use permitting; genuine + TTS + voice-conversion + multi-generator + noise/telephony augmentation) → ④ fine-tune acoustic model (AASIST / wav2vec-WavLM front ends / Whisper-feature branches / multi-stream fusion — one at a time) → ⑤ regional calibration heads (shared encoder + per-language calibration, *not* separate hard-coded detectors) → ⑥ robustness augmentations → ⑦ evaluate on unseen generators.
Split discipline: **speaker-disjoint, generator-disjoint where possible, language/channel/attack stratification.** No fake metrics, ever.

**ASR:** IndicConformer/Whisper → evaluate hi/mr/code-mixed/noisy/telephony → collect failure cases → optional fine-tuning (domain, telephony, accents, scam vocabulary) → track WER/CER per language.

**Scam model:** rules (prototype) → TF-IDF+logistic baseline → transformer/Indic model (LoRA/PEFT if warranted) → calibrated classifier. Labels normal/suspicious/scam + multi-label intents. **Prioritize recall on dangerous categories while controlling false positives.** Metrics: precision/recall/F1/confusion matrix.

## 11. Future MLOps plan (documented, NOT implemented)

data version → experiment tracking → model version → evaluation report → model registry → serving version → monitoring → drift detection → retraining.
Every model card records: name, version, config, training-data version, metrics, **score semantics** (documented per model — no mixing logits and probabilities). Future infra: Docker, MLflow-or-equivalent, object storage, CI/CD, inference workers. **No Kubernetes in the prototype.**

---

## 12. Exact Phase 1 tasks (repo + env + FastAPI skeleton)

Phase 1 was completed under the earlier plan; verified against this v3 spec:

| # | Task | Evidence |
|---|---|---|
| 1 | Repo structure + `.gitignore` | ✅ `voice-clone-shield/` tree |
| 2 | Virtual env + requirements | ✅ `backend/.venv`, pinned deps |
| 3 | FastAPI app, CORS `allow_origins=["*"]` (commented prototype-only), bound `0.0.0.0` | ✅ `app/main.py` |
| 4 | `.env` / `.env.example` with `DEMO_MODE`, `MODEL_PATH`, `ASR_MODEL`, `DEVICE`, `LOG_LEVEL` | ✅ `app/config.py` |
| 5 | `GET /api/health` with per-service status | ✅ live, reports loaded/demo/stateless |
| 6 | Structured logging from day 1 | ✅ `utils/logging_setup.py` |
| 7 | Service placeholders with demo-mode mocks | ✅ (upgraded to real AASIST in Phase 6's slot) |
| 8 | Smoke tests | ✅ 20 passing |
| 9 | Run commands incl. LAN access for phones | ✅ README + `curl` verified from localhost; second-device test pending (Phase 13 gate) |

**Recommendation:** approve Phase 1 as satisfied (evidence above), and start
implementation at **Phase 2 — schemas + database + health**: rewrite
`models/schemas.py` to the frozen contract in §5 (the single blocking item for
every other module), create the SQLite tables (`users`, `voice_profiles`,
`sessions`, `analysis_results`, `threat_events`, `liveness_sessions`), and
extend `/api/health`. Then Phase 4 (the `demo/` mock package) before any more
real models — mocks first is the safety net.
