# demo_data/ — what's real and what isn't (read before presenting!)

**Nothing in this folder is a real scam recording.** Everything here is
synthetically generated. Never present any clip as a real call recording.

| File | What it is | Origin |
|---|---|---|
| `test_tone_16k.wav` | 1 kHz sine tone, 16 kHz mono, 2 s | `scripts/gen_test_audio.py` |
| `test_tone_44k_stereo.wav` | tone, 44.1 kHz stereo (pipeline exercise) | `scripts/gen_test_audio.py` |
| `test_babble_16k.wav` | speech-LIKE babble (sines + noise) — not speech | `scripts/gen_test_audio.py` |
| `test_too_short.wav` | 0.2 s clip that must be rejected by the pipeline | `scripts/gen_test_audio.py` |
| `normal_conversation.wav` | **placeholder** (copy of the tone) for the normal-call demo scenario — replace with a real team recording in Phase 13 | copied file |
| `tts_hindi_scam.mp3` | **TTS-generated** Hindi §3 scam script — used to validate the real ASR path end-to-end | `scripts/generate_tts_samples.py` (gTTS) |
| `tts_marathi_scam.mp3` | **TTS-generated** Marathi §3 scam script | `scripts/generate_tts_samples.py` (gTTS) |
| `tts_hindi_normal.mp3` | **TTS-generated** normal-call control | `scripts/generate_tts_samples.py` (gTTS) |

## Filename hints drive the demo mocks (§DEMO)

When a service runs in demo/mock mode, the **filename** steers the canned
scenario (a presentation aid — no inference):

- `...scam...`, `...fake...`, `...clone...` → HIGH-risk scam scenario
- `...normal...`, `...casual...`, `...genuine...` → LOW-risk normal-call scenario
- anything else → the §3 primary demo

Phase 13 (§21) replaces these placeholders with team-recorded genuine audio +
TTS-generated fakes (`real_hindi.wav`, `fake_marathi.wav`, `hindi_scam.wav`,
a code-mixed sample, `normal_conversation.wav`) — labelled here as they land.
