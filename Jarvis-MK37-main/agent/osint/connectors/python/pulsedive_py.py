"""
Pulsedive — threat intelligence domaine/IP (free tier sans clé).
Cibles : DOMAIN, IP | clé PD_KEY optionnelle pour quotas étendus.
"""
from __future__ import annotations
import os, time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType

_KEY_ENV = "PD_KEY"
_BASE    = "https://pulsedive.com/api"


class PulsediveConnector(Connector):
    name         = "pulsedive_py"
    supports     = {TargetType.DOMAIN, TargetType.IP}
    requires_key = False
    rate_limit   = 30
    backend      = "python"

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        key = os.environ.get(_KEY_ENV, "")
        params: dict = {"indicator": target.normalized, "pretty": 0}
        if key:
            params["key"] = key
        resp = await async_get(f"{_BASE}/info.php", params=params, timeout=12.0)
        elapsed = int((time.monotonic() - t0) * 1000)
        if not resp["ok"]:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error=f"pulsedive {resp['status']}: {str(resp['data'])[:120]}",
                                   elapsed_ms=elapsed)
        d = resp["data"]
        if not isinstance(d, dict) or d.get("error"):
            return ConnectorResult(connector=self.name, target=target, success=True,
                                   findings=[], elapsed_ms=elapsed)
        finding = Finding(
            type="threat_intel",
            source="pulsedive",
            url=f"https://pulsedive.com/indicator/?ioc={target.normalized}",
            extracted={
                "target":      target.normalized,
                "risk":        d.get("risk", "unknown"),
                "risk_score":  d.get("risk_recommended", ""),
                "threats":     [t.get("name", "") for t in d.get("threats", [])[:5]],
                "feeds":       [f.get("name", "") for f in d.get("feeds", [])[:5]],
                "attributes":  d.get("attributes", {}),
                "stamp_added": d.get("stamp_added", ""),
                "stamp_seen":  d.get("stamp_seen", ""),
                "seen_count":  d.get("seen", 0),
            },
            confidence=0.75,
        )
        return ConnectorResult(connector=self.name, target=target, success=True,
                               findings=[finding], elapsed_ms=elapsed)


get_registry().register(PulsediveConnector())
