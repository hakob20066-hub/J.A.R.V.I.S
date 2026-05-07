"""
JARVIS OSINT Engine — Phase 7.6 « Kali Hybrid ».

Public API :
    from agent.osint import get_engine, Target, OSINTReport

    engine = get_engine()
    report = engine.lookup("@fatihmakes", mode="self_audit", depth=2)
"""
from agent.osint.target import Target, TargetType, TargetNormalizer
from agent.osint.engine import OSINTEngine, OSINTReport, get_engine
from agent.osint.safety import LegalGuard, LegalDecision
from agent.osint.audit import OSINTAuditLogger
from agent.osint.kali_runner import KaliRunner, KaliResult, get_runner
from agent.osint.connectors.base import Connector, ConnectorResult, Finding

__all__ = [
    "Target", "TargetType", "TargetNormalizer",
    "OSINTEngine", "OSINTReport", "get_engine",
    "LegalGuard", "LegalDecision",
    "OSINTAuditLogger",
    "KaliRunner", "KaliResult", "get_runner",
    "Connector", "ConnectorResult", "Finding",
]
