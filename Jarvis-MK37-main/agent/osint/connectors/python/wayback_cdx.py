"""
Wayback Machine CDX API — timeline des snapshots d'un domaine.
Cible : DOMAIN | sans clé API.
"""
from __future__ import annotations

import time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType

_CDX_URL = "http://web.archive.org/cdx/search/cdx"


class WaybackCdxConnector(Connector):
    name         = "wayback_cdx"
    supports     = {TargetType.DOMAIN}
    requires_key = False
    rate_limit   = 20
    backend      = "python"

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        domain = target.normalized

        params = {
            "url":        f"*.{domain}/*",
            "output":     "json",
            "fl":         "timestamp,original,statuscode,mimetype",
            "collapse":   "urlkey",
            "limit":      "150",
            "from":       "20100101",
        }
        resp = await async_get(_CDX_URL, params=params, timeout=20.0)
        elapsed = int((time.monotonic() - t0) * 1000)

        if not resp["ok"]:
            return ConnectorResult(
                connector=self.name, target=target, success=False,
                error=f"wayback_cdx {resp['status']}: {str(resp['data'])[:120]}",
                elapsed_ms=elapsed,
            )

        data = resp["data"]
        if not isinstance(data, list) or len(data) < 2:
            return ConnectorResult(
                connector=self.name, target=target, success=True,
                findings=[], elapsed_ms=elapsed,
            )

        headers = data[0]   # premier row = noms de colonnes
        rows    = data[1:]

        try:
            idx = {h: i for i, h in enumerate(headers)}
            ts_i   = idx.get("timestamp", 0)
            url_i  = idx.get("original", 1)
            code_i = idx.get("statuscode", 2)
            mime_i = idx.get("mimetype", 3)
        except Exception:
            return ConnectorResult(
                connector=self.name, target=target, success=False,
                error="wayback_cdx: unexpected schema",
                elapsed_ms=elapsed,
            )

        findings: list[Finding] = []
        for row in rows:
            if not isinstance(row, list) or len(row) < 2:
                continue
            ts  = row[ts_i]   if ts_i  < len(row) else ""
            url = row[url_i]  if url_i < len(row) else ""
            code = row[code_i] if code_i < len(row) else ""
            mime = row[mime_i] if mime_i < len(row) else ""
            if not url:
                continue
            # Convertir timestamp CDX "20231210153042" → ISO
            iso = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}T{ts[8:10]}:{ts[10:12]}:{ts[12:14]}Z" if len(ts) >= 14 else ts
            findings.append(Finding(
                type="wayback_snapshot",
                source="wayback_machine",
                url=f"https://web.archive.org/web/{ts}/{url}",
                extracted={
                    "domain":      domain,
                    "timestamp":   iso,
                    "original_url": url,
                    "status_code": code,
                    "mimetype":    mime,
                    "wayback_url": f"https://web.archive.org/web/{ts}/{url}",
                },
                confidence=0.8,
            ))

        return ConnectorResult(
            connector=self.name, target=target, success=True,
            findings=findings, elapsed_ms=elapsed,
        )


get_registry().register(WaybackCdxConnector())
