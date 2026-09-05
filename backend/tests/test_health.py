"""Phase 1 smoke test (§29): the app starts and /api/health answers.

Run from backend/:
    python -m pytest -v
"""
from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint():
    # Context manager = lifespan (startup) runs, so services get load_all().
    with TestClient(app) as client:
        resp = client.get("/api/health")

    assert resp.status_code == 200
    body = resp.json()

    assert body["status"] == "ok"
    assert body["app"] == "Voice Clone Shield"
    assert body["demo_mode"] is True  # default — §20 demo mode is on
    assert body["privacy_mode"] is True  # privacy-first default (§PRIVACY)
    assert body["database"] == "connected"  # SQLite initialised at startup
    # voice_detector loads the real AASIST-L checkpoint at startup when the
    # file is present (auto-download otherwise); "demo_mode" if unavailable.
    assert body["services"]["voice_detector"] in ("loaded", "demo_mode")
    assert body["services"]["asr_service"] in ("loaded", "demo_mode")  # Phase 5: real backend loads
    assert body["services"]["risk_engine"] == "stateless"
    assert body["services"]["audio_processor"] == "stateless"


def test_root_endpoint():
    with TestClient(app) as client:
        resp = client.get("/")

    assert resp.status_code == 200
    assert resp.json()["health"] == "/api/health"
