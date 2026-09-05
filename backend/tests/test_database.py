"""
Phase 2 tests — SQLite persistence (app/database/database.py).

Key guarantee under test: the schema can store scores/evidence/metadata but
has NO way to store raw audio (privacy-first, §PRIVACY-FIRST).

Run from backend/:  python -m pytest -v
"""
import json
import sqlite3

import pytest

from app.config import settings
from app.database import database as db


@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    """Point the database module at a per-test file and initialise it."""
    monkeypatch.setattr(settings, "DATABASE_PATH", str(tmp_path / "test_shield.db"))
    db.init_db()
    return settings.DATABASE_PATH


CANONICAL = {
    "session_id": "demo-001",
    "status": "complete",
    "audio": {"duration": 23.4, "language": "mr"},
    "voice_trust": {"spoof_risk": 0.91, "speaker_mismatch_risk": None,
                    "overall_voice_risk": 0.84, "status": "SUSPICIOUS"},
    "asr": {"language": "mr", "transcript": "...", "segments": []},
    "scam_analysis": {"risk": 0.88, "category": "Bank/KYC Fraud",
                      "indicators": ["Urgency", "OTP request"]},
    "attack_types": ["AI Voice Impersonation", "Bank Fraud"],
    "risk": {"score": 91, "level": "HIGH"},
    "liveness": {"required": True, "status": "PENDING"},
    "explanation": ["[voice] Synthetic voice evidence detected"],
    "recommendation": "Do not share OTP or transfer money.",
}


def test_all_six_tables_exist(tmp_db):
    conn = sqlite3.connect(tmp_db)
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"users", "voice_profiles", "sessions", "analysis_results",
            "threat_events", "liveness_sessions"} <= names


def test_analysis_roundtrip(tmp_db):
    db.create_session("demo-001", source="upload")
    db.save_analysis_result("demo-001", CANONICAL)

    history = db.get_history()
    assert len(history) == 1
    row = history[0]
    assert row["session_id"] == "demo-001"
    assert row["risk_score"] == 91
    assert row["risk_level"] == "HIGH"
    assert row["attack_types"] == ["AI Voice Impersonation", "Bank Fraud"]
    assert row["result"]["recommendation"].startswith("Do not share OTP")


def test_get_session_returns_results(tmp_db):
    db.create_session("s1")
    db.save_analysis_result("s1", CANONICAL)

    data = db.get_session("s1")
    assert data["session"]["id"] == "s1"
    assert len(data["analysis_results"]) == 1
    assert db.get_session("missing") is None


def test_high_risk_creates_threat_event(tmp_db):
    db.create_session("s1")
    db.save_analysis_result("s1", CANONICAL)  # HIGH

    conn = sqlite3.connect(tmp_db)
    rows = conn.execute("SELECT risk_level, action FROM threat_events").fetchall()
    assert rows == [("HIGH", None)]  # action arrives with PolicyEngine (Phase 10)


def test_low_risk_creates_no_threat_event(tmp_db):
    low = {**CANONICAL, "risk": {"score": 10, "level": "LOW"}}
    db.create_session("s1")
    db.save_analysis_result("s1", low)

    conn = sqlite3.connect(tmp_db)
    assert conn.execute("SELECT COUNT(*) FROM threat_events").fetchone()[0] == 0


def test_liveness_roundtrip(tmp_db):
    db.create_session("s1")
    db.save_liveness("s1", "Blue Tiger 47")
    db.update_liveness_status("s1", "PASSED")

    conn = sqlite3.connect(tmp_db)
    row = conn.execute(
        "SELECT challenge, status, verified_at FROM liveness_sessions").fetchone()
    assert row[0] == "Blue Tiger 47"
    assert row[1] == "PASSED"
    assert row[2] is not None


def test_privacy_no_audio_columns(tmp_db):
    """Schema-level privacy guarantee: no table can hold raw audio."""
    conn = sqlite3.connect(tmp_db)
    forbidden = ("waveform", "audio_blob", "audio_data", "raw_audio")
    for table in ("users", "voice_profiles", "sessions", "analysis_results",
                  "threat_events", "liveness_sessions"):
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        assert not any(f in c.lower() for c in cols for f in forbidden), table


def test_privacy_waveform_payload_rejected(tmp_db):
    """Defence in depth: even a malformed payload carrying a waveform is
    refused at the persistence boundary."""
    poisoned = {**CANONICAL, "waveform": [0.0] * 100}
    with pytest.raises(ValueError, match="PRIVACY"):
        db.save_analysis_result("s1", poisoned)


def test_health_check(tmp_db):
    assert db.check_health() == "connected"
    original = settings.DATABASE_PATH
    try:
        settings.DATABASE_PATH = "/nonexistent_dir_that_cannot_exist/x/y.db"
        assert db.check_health() == "unavailable"
    finally:
        settings.DATABASE_PATH = original
