"""
WebRTC signaling endpoint — WS /ws/webrtc/signal/{session_id} (Phase H, §27).

This is the SIGNALING layer for WebRTC peer connections. It does NOT handle
media streams directly — those go peer-to-peer (or through a TURN server).

Protocol:
  1. Client opens WS /ws/webrtc/signal/{session_id}
  2. Client sends SDP offer/answer and ICE candidates as JSON
  3. Server relays them (in a real multi-party scenario) or uses them to
     set up the server-side peer connection
  4. Once the WebRTC data channel / media track is established, audio
     frames are sent to the /ws/session/{session_id} audio pipeline

PROTOTYPE SCOPE (§2):
  * In this hackathon prototype, we don't run a full WebRTC media server
    (no Janus/mediasoup). Instead, the browser captures audio via
    getUserMedia + AudioWorklet, encodes it to PCM float32, and streams
    it to the existing WebSocket audio endpoint.
  * This signaling endpoint exists to demonstrate the architecture and
    handle the SDP/ICE exchange for future expansion.
  * A production system would use aiortc or a dedicated SFU.
"""
import json
import logging
import uuid
from typing import Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger(__name__)

router = APIRouter(tags=["webrtc"])

# Track connected peers per session (prototype: max 2 peers per session)
_sessions: Dict[str, list] = {}


@router.websocket("/ws/webrtc/signal/{session_id}")
async def webrtc_signal(ws: WebSocket, session_id: str):
    """
    WebRTC signaling relay for a session.

    In the prototype, this primarily serves the browser demo page
    which captures mic audio and pipes it to the analysis WebSocket.
    """
    await ws.accept()
    peer_id = str(uuid.uuid4())[:8]
    log.info("WebRTC signal: peer %s joined session %s", peer_id, session_id)

    if session_id not in _sessions:
        _sessions[session_id] = []
    _sessions[session_id].append({"peer_id": peer_id, "ws": ws})

    try:
        await ws.send_json({
            "type": "welcome",
            "peer_id": peer_id,
            "session_id": session_id,
            "peers": len(_sessions[session_id]),
        })

        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = msg.get("type", "")

            if msg_type in ("offer", "answer", "ice-candidate"):
                # Relay to other peers in the session
                msg["from_peer"] = peer_id
                for peer in _sessions.get(session_id, []):
                    if peer["peer_id"] != peer_id:
                        try:
                            await peer["ws"].send_json(msg)
                        except Exception:
                            pass
                log.debug("WebRTC signal: relayed %s from %s in %s", msg_type, peer_id, session_id)

            elif msg_type == "ping":
                await ws.send_json({"type": "pong", "peer_id": peer_id})

            else:
                await ws.send_json({
                    "type": "error",
                    "message": f"Unknown signal type: {msg_type}",
                })

    except WebSocketDisconnect:
        log.info("WebRTC signal: peer %s left session %s", peer_id, session_id)
    except Exception as exc:
        log.warning("WebRTC signal: error for peer %s — %s", peer_id, exc)
    finally:
        if session_id in _sessions:
            _sessions[session_id] = [
                p for p in _sessions[session_id] if p["peer_id"] != peer_id
            ]
            if not _sessions[session_id]:
                del _sessions[session_id]
