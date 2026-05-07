"""
Connector ABC — base de tous les wrappers OSINT (Kali ou Python).

Voir [[14-Phases/phase7.6-connectors-kali]] et [[14-Phases/phase7.6-connectors-python]].
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from agent.osint.target import Target, TargetType


@dataclass
class Finding:
    type:        str            # account | leak | whois | dns | breach | exif | profile | ...
    source:      str            # site/db/leak name
    url:         Optional[str] = None
    extracted:   dict           = field(default_factory=dict)
    confidence:  float          = 0.5
    pivot_target: Optional[Target] = None  # si peut être ré-introduit dans la cascade

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "source": self.source,
            "url": self.url,
            "extracted": self.extracted,
            "confidence": self.confidence,
        }


@dataclass
class ConnectorResult:
    connector:  str
    target:     Target
    success:    bool
    findings:   list[Finding] = field(default_factory=list)
    raw:        Optional[dict] = None
    elapsed_ms: int = 0
    error:      Optional[str] = None


class Connector(ABC):
    """Wrapper d'une source OSINT (un outil Kali ou une lib Python)."""

    name:           str = "base"
    supports:       set[TargetType] = set()
    requires_key:   bool = False
    rate_limit:     int = 60       # req/h
    backend:        str = "python"  # 'kali' | 'python' | 'docker'

    @abstractmethod
    async def query(self, target: Target) -> ConnectorResult: ...

    def is_available(self) -> bool:
        """Override pour check key/lib/tool."""
        return True

    def supports_target(self, target: Target) -> bool:
        return target.type in self.supports


class ConnectorRegistry:
    """Registry global. Connecteurs s'auto-enregistrent au import."""

    def __init__(self):
        self._connectors: dict[str, Connector] = {}

    def register(self, connector: Connector) -> None:
        self._connectors[connector.name] = connector

    def get(self, name: str) -> Optional[Connector]:
        return self._connectors.get(name)

    def all(self) -> list[Connector]:
        return list(self._connectors.values())

    def for_target(self, target: Target) -> list[Connector]:
        return [c for c in self._connectors.values()
                if c.supports_target(target) and c.is_available()]


_REGISTRY = ConnectorRegistry()


def get_registry() -> ConnectorRegistry:
    return _REGISTRY
