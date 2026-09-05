"""
Phase 9 tests — RiskEngine: v3 5-signal fusion, renormalization, 4-tier
bands, and the per-chunk risk_timeline (§DYNAMIC RISK SCORE).

Run from backend/:  python -m pytest -v
"""
import pytest

from app.risk.risk_engine import WEIGHTS, RiskEngine


@pytest.fixture
def engine():
    return RiskEngine()


# ------------------------------------------------------------- final fusion

def test_renormalization_over_present_signals(engine):
    """voice + scam only (identity/context/liveness have no signal yet):
    weights renormalize to 0.30/0.70 and 0.70 each → (0.93+0.89)*3/7 = 0.78."""
    out = engine.fuse(voice_risk=0.93, scam_risk=0.89, context_risk=0.0)
    assert out["risk_score"] == 78
    assert out["risk_level"] == "HIGH"
    assert out["weights_used"] == {"voice": pytest.approx(3 / 7, abs=1e-3),
                                   "scam": pytest.approx(3 / 7, abs=1e-3),
                                   "context": pytest.approx(1 / 7, abs=1e-3)}


def test_all_five_signals_use_plain_weights(engine):
    out = engine.fuse(voice_risk=1.0, identity_risk=0.5, scam_risk=1.0,
                      context_risk=0.0, liveness_risk=0.0)
    # 0.30 + 0.10 + 0.30 + 0 + 0 = 0.70 → 70
    assert out["risk_score"] == 70
    assert out["weights_used"] == WEIGHTS  # nothing renormalized


def test_identity_signal_is_never_invented(engine):
    """identity=None must be excluded, not defaulted — the signals dump in
    the output keeps the honest None visible."""
    out = engine.fuse(voice_risk=0.5, scam_risk=0.5)
    assert out["signals"]["identity"] is None
    assert "identity" not in out["weights_used"]


def test_no_evidence_is_an_honest_zero(engine):
    out = engine.fuse()
    assert out["risk_score"] == 0 and out["risk_level"] == "LOW"


def test_inputs_are_clamped(engine):
    out = engine.fuse(voice_risk=1.5, scam_risk=-0.2)
    assert 0 <= out["risk_score"] <= 100


# ------------------------------------------------------------------ 4 bands

@pytest.mark.parametrize("score,level", [
    (0, "LOW"), (39, "LOW"), (40, "MEDIUM"), (69, "MEDIUM"),
    (70, "HIGH"), (84, "HIGH"), (85, "CRITICAL"), (100, "CRITICAL"),
])
def test_band_boundaries(engine, score, level):
    assert engine.band(score) == level


# ------------------------------------------------------------------ Risk(t)

def test_timeline_length_and_t_values(engine):
    points = engine.fuse_timeline([0.1] * 6, [None] * 6, context_risk=0.0)
    assert len(points) == 6
    assert [p["t"] for p in points] == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    assert all(p["level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL") for p in points)


def test_timeline_scam_evidence_persists(engine):
    """§DYNAMIC RISK SCORE: Risk(t+1) = Risk(t) + new evidence — once the OTP
    ask appears at t=3, the risk must not fall back at t=4."""
    voice = [0.2, 0.2, 0.2, 0.2, 0.2, 0.2]
    scam = [0.0, 0.3, 0.3, 0.95, None, None]
    points = engine.fuse_timeline(voice, scam, context_risk=0.0)

    assert points[0]["scam_risk"] == 0.0
    assert points[1]["scam_risk"] == 0.3
    assert points[3]["scam_risk"] == 0.95
    assert points[4]["scam_risk"] == 0.95          # persists
    assert points[5]["scam_risk"] == 0.95

    scores = [p["risk_score"] for p in points]
    assert scores[4] >= scores[3] - 1              # not falling when evidence persists
    assert scores[3] > scores[2]                   # the OTP ask RAISED the risk


def test_timeline_is_monotonic_with_constant_signals(engine):
    """Voice and scam constant → risk constant (no invented drift)."""
    points = engine.fuse_timeline([0.8] * 5, [0.9] * 5, context_risk=0.0)
    scores = {p["risk_score"] for p in points}
    assert len(scores) == 1


def test_timeline_voice_only_when_no_segments(engine):
    """IndicConformer path returns no segments → scam None → voice-only
    timeline, and the point-level fusion still renormalizes."""
    points = engine.fuse_timeline([0.99, 0.99], [None, None], context_risk=0.0)
    # voice + context: (0.30*0.99 + 0.10*0)/0.40 = 0.7425 → 74
    assert points[0]["risk_score"] == 74
    assert points[0]["level"] == "HIGH"


# ------------------------------------------------------------------ liveness

def test_liveness_risk_mapping(engine):
    assert engine.liveness_to_risk("PASSED") == 0.0
    assert engine.liveness_to_risk("SUSPICIOUS") == 0.7
    assert engine.liveness_to_risk("FAILED") == 1.0
    assert engine.liveness_to_risk("PENDING") is None   # unknown → no signal
    assert engine.liveness_to_risk(None) is None


def test_fused_score_with_liveness_failure(engine):
    """§ADAPTIVE LIVENESS: a FAILED challenge pushes the final risk up —
    liveness inside the decision loop, not bolted on at the end."""
    before = engine.fuse(voice_risk=0.9, scam_risk=0.9, context_risk=0.0)
    after = engine.fuse(voice_risk=0.9, scam_risk=0.9, context_risk=0.0,
                        liveness_risk=engine.liveness_to_risk("FAILED"))
    assert after["risk_score"] > before["risk_score"]
