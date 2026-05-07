"""
crt.sh — Certificate Transparency → subdomains d'un domaine.
Cible : DOMAIN | sans clé API.
"""
from __future__ import annotations

import time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType


class CrtShConnector(Connector):
    name         = "crtsh"
    supports     = {TargetType.DOMAIN}
    requires_key = False
    rate_limit   = 60
    backend      = "python"

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        domain = target.normalized
        url = "https://crt.sh/"
        params = {"q": f"%.{domain}", "output": "json"}

        resp = await async_get(url, params=params, timeout=15.0)
        elapsed = int((time.monotonic() - t0) * 1000)

        if not resp["ok"] or not isinstance(resp["data"], list):
            return ConnectorResult(
                connector=self.name, target=target, success=False,
                error=f"crtsh {resp['status']}: {str(resp['data'])[:120]}",
                elapsed_ms=elapsed,
            )

        seen: set[str] = set()
        findings: list[Finding] = []
        for entry in resp["data"]:
            if not isinstance(entry, dict):
                continue
            name_val = entry.get("name_value", "") or ""
            issuer   = entry.get("issuer_ca_id", "")
            not_before = entry.get("not_before", "")
            for sub in name_val.splitlines():
                sub = sub.strip().lstrip("*.")
                if sub and sub not in seen and (
                    sub == domain or sub.endswith("." + domain)
                ):
                    seen.add(sub)
                    findings.append(Finding(
                        type="subdomain",
                        source="crtsh",
                        extracted={
                            "subdomain": sub,
                            "domain": domain,
                            "issuer_ca_id": str(issuer),
                            "date": not_before,
                        },
                        confidence=0.9,
                    ))

        return ConnectorResult(
            connector=self.name, target=target, success=True,
            findings=findings, elapsed_ms=elapsed,
        )


get_registry().register(CrtShConnector())
