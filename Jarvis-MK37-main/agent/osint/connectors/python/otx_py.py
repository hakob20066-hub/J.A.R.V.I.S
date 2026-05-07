"""
AlienVault OTX — threat intelligence domaine/IP.
Cibles : DOMAIN, IP | clé OTX_KEY optionnelle (public limité sans clé).
"""
from __future__ import annotations
import os, time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType

_KEY_ENV = "OTX_KEY"
_BASE    = "https://otx.alienvault.com/api/v1"


class OTXConnector(Connector):
    name         = "otx_py"
    supports     = {TargetType.DOMAIN, TargetType.IP}
    requires_key = False
    rate_limit   = 60
    backend      = "python"

    def _headers(self) -> dict:
        key = os.environ.get(_KEY_ENV, "")
        return {"X-OTX-API-KEY": key} if key else {}

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        h = self._headers()
        indicator = "domain" if target.type == TargetType.DOMAIN else "IPv4"
        base_url  = f"{_BASE}/indicators/{indicator}/{target.normalized}"
        findings: list[Finding] = []

        # General
        resp = await async_get(f"{base_url}/general", headers=h, timeout=12.0)
        elapsed = int((time.monotonic() - t0) * 1000)
        if not resp["ok"]:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error=f"otx {resp['status']}: {str(resp['data'])[:120]}",
                                   elapsed_ms=elapsed)
        d = resp["data"]
        if not isinstance(d, dict):
            return ConnectorResult(connector=self.name, target=target, success=True,
                                   findings=[], elapsed_ms=elapsed)
        pulse_info = d.get("pulse_info", {})
        findings.append(Finding(
            type="threat_intel",
            source="otx_alienvault",
            url=f"https://otx.alienvault.com/indicator/{indicator}/{target.normalized}",
            extracted={
                "target":         target.normalized,
                "target_type":    target.type.value,
                "pulse_count":    pulse_info.get("count", 0),
                "malware_count":  len(d.get("malware", [])),
                "url_list_count": len(d.get("url_list", [])),
                "tags":           [p.get("name", "") for p in pulse_info.get("pulses", [])[:5]],
                "reputation":     d.get("reputation", 0),
                "country":        d.get("country_name", ""),
                "asn":            d.get("asn", ""),
                "city":           d.get("city", ""),
            },
            confidence=0.8,
        ))
        return ConnectorResult(connector=self.name, target=target, success=True,
                               findings=findings, elapsed_ms=int((time.monotonic()-t0)*1000))


get_registry().register(OTXConnector())
