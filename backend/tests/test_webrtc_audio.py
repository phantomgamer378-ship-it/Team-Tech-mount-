"""
Tests for the WebRTC + Audio integration endpoints (Phase 8/9/H).

Tests:
  - POST /api/analyze/audio (upload + pipeline)
  - POST /api/liveness/start + /api/liveness/verify
  - WS /ws/session/{id} (audio streaming)
  - Root endpoint shows new endpoints
"""
import io
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def wav_bytes():
    """Generate a valid WAV file in memory (1 second, 16kHz, mono)."""
    import soundfile as sf

    sr = 16000
    duration_s = 1.5
    samples = np.sin(2 * np.pi * 440 * np.linspace(0, duration_s, int(sr * duration_s))).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, samples, sr, format="WAV")
    buf.seek(0)
    return buf.read()


# ------------------------------------------------------------------ Root
class TestRoot:
    def test_root_shows_new_endpoints(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "webrtc_demo" in data
        assert "endpoints" in data
        assert "analyze_audio" in data["endpoints"]
        assert "ws_audio_stream" in data["endpoints"]
        assert "ws_webrtc_signal" in data["endpoints"]


# ------------------------------------------------------------------ Analyze
class TestAnalyzeAudio:
    def test_analyze_empty_file_returns_partial(self, client):
        """An empty file should return status=partial, not a 500."""
        resp = client.post(
            "/api/analyze/audio",
            files={"audio": ("empty.wav", b"", "audio/wav")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "partial"
        assert data["fallback_used"] is True

    def test_analyze_valid_wav(self, client, wav_bytes):
        """A valid WAV should return a full AnalysisResponse."""
        resp = client.post(
            "/api/analyze/audio",
            files={"audio": ("test.wav", wav_bytes, "audio/wav")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"]
        assert data["status"] in ("ok", "partial")
        # Should have voice_analysis, risk at minimum
        if data["status"] == "ok":
            assert data["voice_analysis"] is not None
            assert data["risk"] is not None
            assert data["risk"]["level"] in ("LOW", "MEDIUM", "HIGH")


# ------------------------------------------------------------------ Liveness
class TestLiveness:
    def test_start_and_verify_liveness(self, client):
        """Start a challenge, then verify with the correct phrase."""
        # Start
        resp = client.post(
            "/api/liveness/start",
            json={"session_id": "test-liveness-001"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["required"] is True
        assert data["status"] == "PENDING"
        challenge = data["challenge"]

        # Verify correct
        resp = client.post(
            "/api/liveness/verify",
            json={"session_id": "test-liveness-001", "spoken_text": challenge},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "LIVE"

    def test_wrong_liveness_response(self, client):
        """Wrong phrase should return SUSPICIOUS."""
        client.post("/api/liveness/start", json={"session_id": "test-wrong-001"})
        resp = client.post(
            "/api/liveness/verify",
            json={"session_id": "test-wrong-001", "spoken_text": "wrong answer"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUSPICIOUS"

    def test_verify_without_start(self, client):
        """Verify without start should return FAILED."""
        resp = client.post(
            "/api/liveness/verify",
            json={"session_id": "no-such-session"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "FAILED"


# ------------------------------------------------------------------ WebSocket
class TestWebSocket:
    def test_ws_session_connect_and_end(self, client):
        """Connect, send end immediately, get analysis_complete."""
        with client.websocket_connect("/ws/session/test-ws-001") as ws:
            # Should receive session_start
            msg = ws.receive_json()
            assert msg["type"] == "session_start"
            assert msg["session_id"] == "test-ws-001"

            # Send end without any audio
            ws.send_json({"type": "end"})

            # Should get status messages and then analysis_complete
            messages = []
            for _ in range(10):  # consume up to 10 messages
                msg = ws.receive_json()
                messages.append(msg)
                if msg["type"] == "analysis_complete":
                    break

            final = messages[-1]
            assert final["type"] == "analysis_complete"
            assert final["status"] == "partial"  # no audio → partial

    def test_ws_session_with_audio_chunks(self, client):
        """Send a couple of PCM chunks and get analysis."""
        with client.websocket_connect("/ws/session/test-ws-002") as ws:
            ws.receive_json()  # session_start

            # Generate and send 2 chunks (1 second each, 16kHz float32)
            for i in range(2):
                chunk = np.sin(
                    2 * np.pi * 440 * np.linspace(0, 1, 16000)
                ).astype(np.float32)
                ws.send_bytes(chunk.tobytes())
                ack = ws.receive_json()
                assert ack["type"] == "chunk_ack"
                assert ack["chunk_index"] == i + 1

            # End
            ws.send_json({"type": "end"})

            # Consume until analysis_complete
            result = None
            for _ in range(20):
                msg = ws.receive_json()
                if msg["type"] == "analysis_complete":
                    result = msg
                    break
            assert result is not None
            assert result["chunks_received"] == 2
            assert result["duration_s"] > 0

    def test_ws_ping_pong(self, client):
        """Ping should return pong."""
        with client.websocket_connect("/ws/session/test-ws-ping") as ws:
            ws.receive_json()  # session_start
            ws.send_json({"type": "ping"})
            msg = ws.receive_json()
            assert msg["type"] == "pong"


# ------------------------------------------------------------------ WebRTC Signal
class TestWebRTCSignal:
    def test_webrtc_signal_connect(self, client):
        """Connect to signaling and receive welcome."""
        with client.websocket_connect("/ws/webrtc/signal/test-rtc-001") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "welcome"
            assert msg["session_id"] == "test-rtc-001"
            assert "peer_id" in msg

    def test_webrtc_signal_ping_pong(self, client):
        """Ping should return pong."""
        with client.websocket_connect("/ws/webrtc/signal/test-rtc-ping") as ws:
            ws.receive_json()  # welcome
            ws.send_text(json.dumps({"type": "ping"}))
            msg = ws.receive_json()
            assert msg["type"] == "pong"
