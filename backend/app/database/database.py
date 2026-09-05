"""
SQLite persistence (§DATABASE) — prototype store.

Tables (v3 master prompt): users, voice_profiles, sessions, analysis_results,
threat_events, liveness_sessions.

PRIVACY-FIRST (§PRIVACY-FIRST) — enforced by schema design:
  * there is NO column anywhere that can hold raw audio;
  * analysis_results stores extracted fields + the canonical response JSON
    (scores/evidence/text), never waveforms;
  * voice_profiles stores reference METADATA only — the speaker-embedding
    reference arrives in Phase 16 and will be an embedding, not audio.

PROTOTYPE: stdlib sqlite3, one short-lived connection per operation (safe
across FastAPI's thread pool), path resolved from settings at call time so
tests can point it at a temp file. FUTURE: Postgres behind these same functions.

PRODUCTION WOULD DO BETTER (§23): encryption at rest, consent + retention
policies, anonymization, audit logs.
"""
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS voice_profiles (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER REFERENCES users(id),
    label          TEXT NOT NULL,              -- e.g. "mom", "team-lead"
    reference_meta TEXT,                       -- Phase 16: speaker embedding reference; metadata only
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,               -- session_id
    source     TEXT,                           -- upload | mic | ws | demo
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_results (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT,
    created_at   TEXT NOT NULL,
    duration_s   REAL,
    language     TEXT,
    spoof_risk   REAL,
    scam_risk    REAL,
    risk_score   INTEGER,
    risk_level   TEXT,
    attack_types TEXT,                         -- JSON array
    indicators   TEXT,                         -- JSON array
    fallback_used INTEGER DEFAULT 0,
    result_json  TEXT NOT NULL                 -- full canonical response (no audio by design)
);

CREATE TABLE IF NOT EXISTS threat_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT,
    created_at   TEXT NOT NULL,
    risk_level   TEXT NOT NULL,
    attack_types TEXT,                         -- JSON array
    action       TEXT                          -- policy action, e.g. VERIFY_CALLER
);

CREATE TABLE IF NOT EXISTS liveness_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT,
    challenge   TEXT NOT NULL,
    status      TEXT NOT NULL,                 -- PENDING | PASSED | SUSPICIOUS | FAILED
    created_at  TEXT NOT NULL,
    verified_at TEXT
);
"""

# Levels that count as a threat event worth recording (policy wiring lands
# with the PolicyEngine — until then the rule is simply "MEDIUM and above").
THREAT_LEVELS = ("MEDIUM", "HIGH", "CRITICAL")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    path = Path(settings.DATABASE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create all tables. Called ONCE at startup (main.py lifespan)."""
    with _connect() as conn:
        conn.executescript(SCHEMA)
    log.info("Database ready at %s", settings.DATABASE_PATH)


def check_health() -> str:
    """'connected' | 'unavailable' — surfaced by /api/health."""
    try:
        with _connect() as conn:
            conn.execute("SELECT 1")
        return "connected"
    except Exception as exc:  # §20 — report, never raise
        log.warning("Database health check failed: %s", exc)
        return "unavailable"


def _ensure_session(conn: sqlite3.Connection, session_id: str, source: str = "upload") -> None:
    conn.execute(
        "INSERT OR IGNORE INTO sessions (id, source, created_at) VALUES (?, ?, ?)",
        (session_id, source, _now()),
    )


# ------------------------------------------------------------------ writes

def create_session(session_id: str, source: str = "upload") -> str:
    """Create a session row; returns its created_at timestamp."""
    created = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sessions (id, source, created_at) VALUES (?, ?, ?)",
            (session_id, source, created),
        )
    return created


def save_analysis_result(session_id: str, response: Dict[str, Any]) -> None:
    """Persist one canonical AnalysisResponse dict (metadata + scores only).

    PRIVACY: `response` must never contain a waveform — the contract's
    AudioInfo is metadata-only, and this function rejects a payload that
    carries one, so a future refactor can't silently leak audio.
    """
    flat = json.dumps(response, ensure_ascii=False)
    if '"waveform"' in flat:
        raise ValueError("PRIVACY violation: refusing to persist a response containing a waveform")

    risk = response.get("risk") or {}
    voice = response.get("voice_trust") or {}
    scam = response.get("scam_analysis") or {}
    audio = response.get("audio") or {}
    asr = response.get("asr") or {}
    language = asr.get("language") or audio.get("language")

    with _connect() as conn:
        _ensure_session(conn, session_id)
        conn.execute(
            """
            INSERT INTO analysis_results
              (session_id, created_at, duration_s, language, spoof_risk, scam_risk,
               risk_score, risk_level, attack_types, indicators, fallback_used, result_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                _now(),
                audio.get("duration"),
                language,
                voice.get("spoof_risk"),
                scam.get("risk"),
                risk.get("score"),
                risk.get("level"),
                json.dumps(response.get("attack_types", [])),
                json.dumps((scam.get("indicators") or [])),
                1 if response.get("fallback_used") else 0,
                flat,
            ),
        )

    # A HIGH/CRITICAL result is also a threat event (policy action lands later).
    if risk.get("level") in THREAT_LEVELS:
        save_threat_event(
            session_id=session_id,
            risk_level=risk["level"],
            attack_types=response.get("attack_types", []),
            action=None,  # PolicyEngine decision wired in Phase 10
        )


def save_threat_event(session_id: str, risk_level: str,
                      attack_types: List[str], action: Optional[str]) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO threat_events (session_id, created_at, risk_level, attack_types, action)"
            " VALUES (?, ?, ?, ?, ?)",
            (session_id, _now(), risk_level, json.dumps(attack_types), action),
        )


def save_liveness(session_id: str, challenge: str) -> None:
    with _connect() as conn:
        _ensure_session(conn, session_id)
        conn.execute(
            "INSERT INTO liveness_sessions (session_id, challenge, status, created_at)"
            " VALUES (?, ?, 'PENDING', ?)",
            (session_id, challenge, _now()),
        )


def update_liveness_status(session_id: str, status: str) -> None:
    """Update the most recent PENDING challenge for this session."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM liveness_sessions WHERE session_id = ? AND status = 'PENDING'"
            " ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        if row is None:
            log.warning("No PENDING liveness challenge for session=%s", session_id)
            return
        conn.execute(
            "UPDATE liveness_sessions SET status = ?, verified_at = ? WHERE id = ?",
            (status, _now(), row["id"]),
        )


# ------------------------------------------------------------------- reads

def get_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Recent analysis results, newest first (GET /api/history)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM analysis_results ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["attack_types"] = json.loads(item.pop("attack_types") or "[]")
        item["indicators"] = json.loads(item.pop("indicators") or "[]")
        item["result"] = json.loads(item.pop("result_json"))
        out.append(item)
    return out


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Session row + its analysis results (GET /api/session/{id})."""
    with _connect() as conn:
        sess = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if sess is None:
            return None
        rows = conn.execute(
            "SELECT * FROM analysis_results WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
    results = []
    for r in rows:
        item = dict(r)
        item["attack_types"] = json.loads(item.pop("attack_types") or "[]")
        item["indicators"] = json.loads(item.pop("indicators") or "[]")
        item["result"] = json.loads(item.pop("result_json"))
        results.append(item)
    return {"session": dict(sess), "analysis_results": results}
