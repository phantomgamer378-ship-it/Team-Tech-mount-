"""
Phase 11 tests — the HTTP API (§12/§13): session, analyze/audio, liveness,
history. Every response must fit one of the two frozen contract shapes.

Demo-mode tests run the fast deterministic mocks; one real-model test
exercises the true pipeline end-to-end (skipped when models are unavailable).

Run from backend/:  python -m pytest -v
"""
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.models.schemas import AnalysisResponse, FallbackResponse
from app.services import ServiceContainer

REPO = Path(__file__).resolve().parent.parent.parent
DEMO_AUDIO = REPO / "demo_data" / "test_tone_16k.wav"
REAL_AUDIO = REPO / "demo_data" / "tts_hindi_scam.mp3"


@pytest.fixture(scope="module")
def demo_client():
    """TestClient wired to the ALL-DEMO container (fast, deterministic)."""
    from app.main import app

    settings.USE_DEMO_SERVICES = True
    original_services = app.state.services
    app.state.services = ServiceContainer.create()
    try:
        with TestClient(app) as c:  # context manager runs startup (lifespan)
            yield c
    finally:
        settings.USE_DEMO_SERVICES = False
        app.state.services = original_services


def _upload(client, path: Path, lang: str = "hi", **extra):
    with open(path, "rb") as fh:
        return client.post(
            "/api/analyze/audio",
            files={"file": (path.name, fh, "audio/wav")},
            data={"lang": lang, **extra},
        )


# ----------------------------------------------------------------- session

def test_create_session(demo_client):
    r = demo_client.post("/api/session", json={"source": "test"})
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] and body["created_at"] and body["source"] == "test"


# ------------------------------------------------- analyze/audio (demo mode)

def test_analyze_audio_canonical_shape(demo_client):
    r = _upload(demo_client, DEMO_AUDIO)
    assert r.status_code == 200
    body = r.json()

    model = AnalysisResponse(**body)  # contract validation — raises on drift
    assert model.status == "complete"
    assert model.risk.level in ("MEDIUM", "HIGH")   # demo scam+voice scenario
    assert len(model.risk_timeline) >= 1            # Risk(t) present
    assert model.liveness.required is True          # HIGH → challenge
    assert any(e.startswith("[voice]") for e in model.explanation)
    assert any(e.startswith("[scam_rule]") for e in model.explanation)
    assert any(e.startswith("[fused]") for e in model.explanation)
    assert "OTP" in model.recommendation


def test_analyze_audio_corrupt_file_returns_fallback(demo_client):
    r = demo_client.post(
        "/api/analyze/audio",
        files={"file": ("bad.wav", io.BytesIO(b"definitely not audio"), "audio/wav")},
    )
    assert r.status_code == 200
    body = r.json()
    assert FallbackResponse(**body).fallback_used is True  # never a raw 500


def test_analyze_audio_rejects_wrong_type(demo_client):
    r = demo_client.post(
        "/api/analyze/audio",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    body = r.json()
    assert body["status"] == "partial" and "Unsupported audio type" in body["error"]


def test_analyze_audio_rejects_bad_lang(demo_client):
    r = _upload(demo_client, DEMO_AUDIO, lang="fr")
    assert "lang must be" in r.json()["error"]


# ------------------------------------------------------------- liveness flow

def test_liveness_start_verify_flow(demo_client):
    sid = demo_client.post("/api/session", json={"source": "liveness"}).json()["session_id"]

    r = demo_client.post("/api/liveness/start", json={"session_id": sid})
    assert r.status_code == 200
    started = r.json()
    assert started["status"] == "PENDING" and started["challenge"]

    ok = demo_client.post(
        "/api/liveness/verify",
        json={"session_id": sid, "spoken_text": started["challenge"]},
    ).json()
    assert ok["status"] == "PASSED"

    demo_client.post("/api/liveness/start", json={"session_id": sid})
    bad = demo_client.post(
        "/api/liveness/verify",
        json={"session_id": sid, "spoken_text": "wrong phrase"},
    ).json()
    assert bad["status"] == "SUSPICIOUS"


def test_liveness_verify_without_start_fails_closed(demo_client):
    body = demo_client.post(
        "/api/liveness/verify", json={"session_id": "never-started", "spoken_text": "x"}
    ).json()
    assert body["status"] == "FAILED"


# --------------------------------------------------- persistence & history

def test_analyze_then_history_and_session(demo_client):
    analyze = _upload(demo_client, DEMO_AUDIO).json()
    sid = analyze["session_id"]

    history = demo_client.get("/api/history?limit=5").json()
    assert history["count"] >= 1
    assert any(item["session_id"] == sid for item in history["history"])

    sess = demo_client.get(f"/api/session/{sid}").json()
    assert sess["session"]["id"] == sid
    assert len(sess["analysis_results"]) >= 1

    missing = demo_client.get("/api/session/does-not-exist").json()
    assert missing["status"] == "partial" and missing["fallback_used"] is True


# ------------------------------------------------------------- real pipeline

@pytest.fixture(scope="module")
def real_client():
    """TestClient on the REAL services (skipped when models unavailable)."""
    from app.main import app

    # Force a real container regardless of module fixture order — the demo
    # fixture (same module) keeps USE_DEMO_SERVICES=True until module teardown.
    original_flag = settings.USE_DEMO_SERVICES
    settings.USE_DEMO_SERVICES = False
    container = ServiceContainer.create()
    try:
        if not (container.voice_detector.load_model() and container.asr_service.load_model()):
            pytest.skip("Real models unavailable — real API test skipped")
        original_services = app.state.services
        app.state.services = container
        with TestClient(app) as c:
            yield c
        app.state.services = original_services
    finally:
        settings.USE_DEMO_SERVICES = original_flag


def test_analyze_audio_real_models(real_client):
    if not REAL_AUDIO.exists():
        pytest.skip("demo_data/tts_hindi_scam.mp3 missing (run scripts/generate_tts_samples.py)")

    r = _upload(real_client, REAL_AUDIO)
    assert r.status_code == 200
    body = r.json()

    model = AnalysisResponse(**body)
    assert body["voice_trust"]["model"].startswith("aasist")
    assert body["asr"]["model"] != "mock_fallback"
    assert body["scam_analysis"]["category"] == "Bank/KYC Fraud"
    assert body["risk"]["level"] in ("HIGH", "CRITICAL")
    assert body["attack_types"] and "AI Voice Impersonation" in body["attack_types"]
    assert len(body["risk_timeline"]) >= 3           # 5.6 s clip → ~5 points
    assert model.status == "complete"
