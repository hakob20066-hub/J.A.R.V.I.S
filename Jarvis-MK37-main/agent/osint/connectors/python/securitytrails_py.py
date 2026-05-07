"""
SecurityTrails — historique DNS + sous-domaines + whois historique.
Cibles : DOMAIN | clé ST_API_KEY requise.
"""
from __future__ import annotations
import os, time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType

_KEY_ENV = "ST_API_KEY"
_BASE    = "https://api.securitytrails.com/v1"


class SecurityTrailsConnector(Connector):
    name         = "securitytrails_py"
    supports     = {TargetType.DOMAIN}
    requires_key = True
    rate_limit   = 50
    backend      = "python"

    def _key(self): return os.environ.get(_KEY_ENV, "")
    def is_available(self): return bool(self._key())

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        key = self._key()
        if not key:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error="ST_API_KEY not set", elapsed_ms=0)
        h = {"APIKEY": key, "Accept": "application/json"}
        domain = target.normalized
        findings: list[Finding] = []

        import asyncio
        # Subdomains + DNS history en parallèle
        sub_resp, dns_resp = await asyncio.gather(
            async_get(f"{_BASE}/domain/{domain}/subdomains", headers=h, timeout=12.0),
            async_get(f"{_BASE}/history/{domain}/dns/a", headers=h, timeout=12.0),
        )
        elapsed = int((time.monotonic() - t0) * 1000)

        # Subdomains
        if sub_resp["ok"] and isinstance(sub_resp["data"], dict):
            for sub in sub_resp["data"].get("subdomains", [])[:50]:
                findings.append(Finding(
                    type="subdomain",
                    source="securitytrails",
                    extracted={"domain": domain, "subdomain": f"{sub}.{domain}"},
                    confidence=0.9,
                ))

        # DNS A history
        if dns_resp["ok"] and isinstance(dns_resp["data"], dict):
            for record in dns_resp["data"].get("records", [])[:20]:
                for val in record.get("values", []):
                    findings.append(Finding(
                        type="dns_history",
                        source="securitytrails",
                        extracted={
                            "domain":       domain,
                            "record_type":  "A",
                            "ip":           val.get("ip", ""),
                            "first_seen":   record.get("first_seen", ""),
                            "last_seen":    record.get("last_seen", ""),
                        },
                        confidence=0.85,
                    ))

        return ConnectorResult(connector=self.name, target=target, success=True,
                               findings=findings, elapsed_ms=elapsed,
                               error=None if findings else "no data")


get_registry().register(SecurityTrailsConnector())
