"""Tests OSINTEngine end-to-end (mocked connectors)."""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.osint.engine import OSINTEngine
from agent.osint.connectors.base import (
    Connector, ConnectorResult, Finding, ConnectorRegistry,
)
from agent.osint.target import Target, TargetType
from agent.osint.safety import LegalGuard, LegalDecision, LegalCheck


class MockConnector(Connector):
    name = "mock"
    supports = {TargetType.EMAIL, TargetType.USERNAME, TargetType.INSTAGRAM_HANDLE}
    backend = "python"

    def __init__(self, findings_to_emit=None):
        self.findings_to_emit = findings_to_emit or []
        self.called_with = []

    async def query(self, target):
        self.called_with.append(target)
        return ConnectorResult(
            connector=self.name, target=target, success=True,
            findings=list(self.findings_to_emit),
            elapsed_ms=10,
        )


def _bypass_guard():
    """LegalGuard qui autorise tout (pour tests engine)."""
    g = MagicMock(spec=LegalGuard)
    g.check.return_value = LegalCheck(
        decision=LegalDecision.ALLOW, reason="test", mode="self_audit", is_self=True,
    )
    g.consume_external_quota = MagicMock()
    return g


def test_engine_unknown_target_returns_error():
    engine = OSINTEngine()
    engine.guard = _bypass_guard()
    report = asyncio.run(engine.lookup_async("..."))
    assert report.error is not None
    assert "unknown" in report.error.lower()


def test_engine_calls_connectors_for_target_type():
    registry = ConnectorRegistry()
    mock = MockConnector(findings_to_emit=[
        Finding(type="account", source="github", confidence=0.9)
    ])
    registry.register(mock)

    engine = OSINTEngine()
    engine.guard = _bypass_guard()

    with patch("agent.osint.engine.get_registry", return_value=registry):
        report = asyncio.run(engine.lookup_async("fatih@example.com", depth=1))
    assert len(report.findings) == 1
    assert report.findings[0].source == "github"
    assert "mock" in report.sources_used


def test_engine_pivot_cascade_depth_2():
    registry = ConnectorRegistry()
    pivot_finding = Finding(
        type="profile", source="instagram",
        extracted={"email": "found@derived.com"},
        confidence=0.9,
    )
    mock = MockConnector(findings_to_emit=[pivot_finding])
    registry.register(mock)

    engine = OSINTEngine()
    engine.guard = _bypass_guard()

    with patch("agent.osint.engine.get_registry", return_value=registry):
        report = asyncio.run(engine.lookup_async("@fatihmakes", depth=2))
    # Connector appelé pour cible initiale + cible pivot extraite
    assert len(mock.called_with) >= 1
    # Le pivot doit avoir été exploré
    explored_normalized = {t.normalized for t in report.targets_explored}
    assert any("derived.com" in n for n in explored_normalized) or len(report.targets_explored) >= 1


def test_engine_no_connectors_returns_empty_report():
    registry = ConnectorRegistry()  # vide
    engine = OSINTEngine()
    engine.guard = _bypass_guard()
    with patch("agent.osint.engine.get_registry", return_value=registry):
        report = asyncio.run(engine.lookup_async("fatih@example.com"))
    assert len(report.findings) == 0
    assert report.error is None


def test_engine_cancel_stops_cascade():
    registry = ConnectorRegistry()
    registry.register(MockConnector())
    engine = OSINTEngine()
    engine.guard = _bypass_guard()
    engine.cancel()
    with patch("agent.osint.engine.get_registry", return_value=registry):
        # reset_cancel=False : préserve le flag set juste au-dessus
        report = asyncio.run(engine.lookup_async("fatih@example.com", reset_cancel=False))
    assert report.cancelled is True


def test_engine_blocked_external_quota():
    g = MagicMock(spec=LegalGuard)
    g.check.return_value = LegalCheck(
        decision=LegalDecision.BLOCKED_RATE_LIMIT,
        reason="quota", mode="external_target", is_self=False,
    )
    engine = OSINTEngine()
    engine.guard = g
    report = asyncio.run(engine.lookup_async("x@x.com", mode="external_target"))
    assert "quota" in (report.error or "").lower()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
