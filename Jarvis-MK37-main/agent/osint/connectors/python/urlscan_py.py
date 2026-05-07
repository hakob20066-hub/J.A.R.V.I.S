"""
URLScan.io — historique de scans publics pour un domaine.
Cibles : DOMAIN | sans clé (search public), clé URLSCAN_KEY pour soumissions.
"""
from __future__ import annotations
import time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType

_BASE = "https://urlscan.io/api/v1"


class UrlScanConnector(Connector):
    name         = "urlscan_py"
    supports     = {TargetType.DOMAIN}
    requires_key = False
    rate_limit   = 60
    backend      = "python"

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        domain = target.normalized
        resp = await async_get(f"{_BASE}/search/",
                               params={"q": f"domain:{domain}", "size": 20},
                               timeout=12.0)
        elapsed = int((time.monotonic() - t0) * 1000)
        if not resp["ok"]:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error=f"urlscan {resp['status']}: {str(resp['data'])[:120]}",
                                   elapsed_ms=elapsed)
        data = resp["data"]
        if not isinstance(data, dict):
            return ConnectorResult(connector=self.name, target=target, success=True,
                                   findings=[], elapsed_ms=elapsed)
        findings: list[Finding] = []
        for result in data.get("results", []):
            page  = result.get("page", {})
            scan  = result.get("stats", {})
            task  = result.get("task", {})
            findings.append(Finding(
                type="url_scan",
                source="urlscan.io",
                url=result.get("result", ""),
                extracted={
                    "domain":      domain,
                    "scanned_url": page.get("url", ""),
                    "ip":          page.get("ip", ""),
                    "country":     page.get("country", ""),
                    "server":      page.get("server", ""),
                    "title":       page.get("title", ""),
                    "malicious":   scan.get("malicious", 0),
                    "timestamp":   task.get("time", ""),
                    "screenshot":  result.get("screenshot", ""),
                },
                confidence=0.75,
            ))
        return ConnectorResult(connector=self.name, target=target, success=True,
                               findings=findings, elapsed_ms=elapsed)


get_registry().register(UrlScanConnector())
