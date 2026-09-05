"""
Phase 10 tests — PolicyEngine (§POLICY ENGINE): pure tier → action mapping.
"""
import pytest

from app.risk.policy_engine import decide


@pytest.mark.parametrize("level,action", [
    ("LOW", "CONTINUE"),
    ("MEDIUM", "CAUTION"),
    ("HIGH", "VERIFY_CALLER"),
    ("CRITICAL", "WARN"),
])
def test_every_tier_maps_to_its_action(level, action):
    assert decide(level) == action


def test_unknown_level_fails_safe():
    """Never fail open: an unrecognized level gets the most protective action."""
    assert decide("EXTREME") == "WARN"
    assert decide("") == "WARN"
    assert decide(None) == "WARN"  # type: ignore[arg-type]
