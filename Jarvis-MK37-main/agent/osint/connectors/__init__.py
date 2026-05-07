"""OSINT connectors — Kali wrappers + Python fallbacks."""
from agent.osint.connectors.base import (
    Connector, ConnectorResult, Finding, ConnectorRegistry, get_registry,
)
import agent.osint.connectors.python  # noqa: F401 — auto-enregistre les 10 connecteurs Python

__all__ = ["Connector", "ConnectorResult", "Finding", "ConnectorRegistry", "get_registry"]
