"""Tests LegalGuard Phase 7.6."""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.osint.safety import LegalGuard, LegalDecision, EXTERNAL_DAILY_LIMIT
from agent.osint.target import TargetNormalizer, TargetType, Target


def _guard_with_identities(identities: dict, rate_state: dict = None) -> LegalGuard:
    g = LegalGuard()
    g.identities = identities
    if rate_state is not None:
        with patch("agent.osint.safety._load_rate_state", return_value=rate_state), \
             patch("agent.osint.safety._save_rate_state"):
            return g
    return g


def test_self_email_allowed():
    g = _guard_with_identities({"emails": ["fatih@example.com"]})
    target = TargetNormalizer.detect("fatih@example.com")
    decision = g.check(target, mode="self_audit")
    assert decision.decision == LegalDecision.ALLOW
    assert decision.is_self is True


def test_self_handle_instagram():
    g = _guard_with_identities({"handles": {"instagram": "@fatihmakes"}})
    target = TargetNormalizer.detect("@fatihmakes")
    decision = g.check(target, mode="self_audit")
    assert decision.decision == LegalDecision.ALLOW
    assert decision.is_self is True


def test_external_target_requires_disclaimer():
    g = LegalGuard()
    g.identities = {}
    with patch("agent.osint.safety._load_rate_state", return_value={"external": {}}):
        target = TargetNormalizer.detect("unknown@external.com")
        decision = g.check(target, mode="external_target")
        assert decision.decision == LegalDecision.REQUIRE_DISCLAIMER


def test_external_quota_blocks():
    import time
    today = time.strftime("%Y-%m-%d")
    g = LegalGuard()
    g.identities = {}
    state = {"external": {today: EXTERNAL_DAILY_LIMIT}}
    with patch("agent.osint.safety._load_rate_state", return_value=state):
        target = TargetNormalizer.detect("unknown@external.com")
        decision = g.check(target, mode="external_target")
        assert decision.decision == LegalDecision.BLOCKED_RATE_LIMIT


def test_image_face_recognition_blocked_by_default():
    """deep=True sur image → refus par défaut."""
    g = LegalGuard()
    g.identities = {}
    # Crée un Target image manuellement (path n'a pas besoin d'exister pour ce test)
    target = Target(raw="x.jpg", type=TargetType.IMAGE, normalized="/tmp/x.jpg")
    decision = g.check(target, mode="self_audit", deep=True)
    assert decision.decision == LegalDecision.BLOCKED_DEFAULT_REFUSAL


def test_record_consent_returns_id():
    g = LegalGuard()
    g.identities = {}
    target = TargetNormalizer.detect("user@x.com")
    with tempfile.TemporaryDirectory() as tmp:
        consent_path = Path(tmp) / "consent.log"
        with patch("agent.osint.safety.CONSENT_LOG", consent_path):
            cid = g.record_consent(target, popup_version="v1")
            assert cid.startswith("consent_v1_")
            assert consent_path.exists()
            content = consent_path.read_text(encoding="utf-8")
            assert target.hash() in content


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
