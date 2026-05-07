"""
LeakCheck.io — vérification email dans bases leakées.
Cibles : EMAIL | clé LEAKCHECK_KEY requise.
"""
from __future__ import annotations
import os, time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType

_KEY_ENV = "LEAKCHECK_KEY"
_BASE    = "https://leakcheck.io/api/v2"


class LeakCheckConnector(Connector):
    name         = "leakcheck_py"
    supports     = {TargetType.EMAIL}
    requires_key = True
    rate_limit   = 30
    backend      = "python"

    def _key(self): return os.environ.get(_KEY_ENV, "")
    def is_available(self): return bool(self._key())

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        key = self._key()
        if not key:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error="LEAKCHECK_KEY not set", elapsed_ms=0)
        resp = await async_get(f"{_BASE}/query/{target.normalized}",
                               headers={"X-API-Key": key}, timeout=12.0)
        elapsed = int((time.monotonic() - t0) * 1000)
        if not resp["ok"]:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error=f"leakcheck {resp['status']}: {str(resp['data'])[:120]}",
                                   elapsed_ms=elapsed)
        d = resp["data"]
        if not isinstance(d, dict) or not d.get("success"):
            return ConnectorResult(connector=self.name, target=target, success=True,
                                   findings=[], elapsed_ms=elapsed)
        findings: list[Finding] = []
        for source in d.get("sources", []):
            findings.append(Finding(
                type="breach",
                source="leakcheck",
                extracted={
                    "email":       target.normalized,
                    "leak_name":   source.get("name", ""),
                    "leak_date":   source.get("breach_date", ""),
                    "leak_type":   source.get("leak_type", ""),
                    "leak_fields": source.get("fields", []),
                },
                confidence=0.85,
            ))
        return ConnectorResult(connector=self.name, target=target, success=True,
                               findings=findings, elapsed_ms=elapsed)


get_registry().register(LeakCheckConnector())
