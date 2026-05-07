"""
VirusTotal — passive DNS + réputation domaine/IP.
Cibles : DOMAIN, IP | clé VT_API_KEY requise.
"""
from __future__ import annotations
import os, time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType

_KEY_ENV = "VT_API_KEY"
_BASE    = "https://www.virustotal.com/api/v3"


class VirusTotalConnector(Connector):
    name         = "virustotal_py"
    supports     = {TargetType.DOMAIN, TargetType.IP}
    requires_key = True
    rate_limit   = 4    # free tier : 4 req/min
    backend      = "python"

    def _key(self): return os.environ.get(_KEY_ENV, "")
    def is_available(self): return bool(self._key())

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        key = self._key()
        if not key:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error="VT_API_KEY not set", elapsed_ms=0)
        endpoint = "domains" if target.type == TargetType.DOMAIN else "ip_addresses"
        url = f"{_BASE}/{endpoint}/{target.normalized}"
        resp = await async_get(url, headers={"x-apikey": key}, timeout=15.0)
        elapsed = int((time.monotonic() - t0) * 1000)
        if resp["status"] == 404:
            return ConnectorResult(connector=self.name, target=target, success=True,
                                   findings=[], elapsed_ms=elapsed)
        if not resp["ok"]:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error=f"vt {resp['status']}: {str(resp['data'])[:120]}",
                                   elapsed_ms=elapsed)
        d = resp["data"]
        if not isinstance(d, dict):
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error="vt: unexpected response", elapsed_ms=elapsed)
        attrs = d.get("data", {}).get("attributes", {}) if "data" in d else d.get("attributes", {})
        stats = attrs.get("last_analysis_stats", {})
        findings = [Finding(
            type="reputation",
            source="virustotal",
            url=f"https://www.virustotal.com/gui/{endpoint}/{target.normalized}",
            extracted={
                "target":        target.normalized,
                "target_type":   target.type.value,
                "malicious":     stats.get("malicious", 0),
                "suspicious":    stats.get("suspicious", 0),
                "harmless":      stats.get("harmless", 0),
                "undetected":    stats.get("undetected", 0),
                "reputation":    attrs.get("reputation", 0),
                "categories":    attrs.get("categories", {}),
                "tags":          attrs.get("tags", []),
                "registrar":     attrs.get("registrar", ""),
                "country":       attrs.get("country", ""),
                "as_owner":      attrs.get("as_owner", ""),
                "last_analysis": attrs.get("last_analysis_date", ""),
            },
            confidence=0.9,
        )]
        return ConnectorResult(connector=self.name, target=target, success=True,
                               findings=findings, elapsed_ms=elapsed)


get_registry().register(VirusTotalConnector())
