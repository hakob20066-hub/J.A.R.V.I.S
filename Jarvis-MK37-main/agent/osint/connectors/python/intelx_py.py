"""
IntelX — recherche leaks/pastes/dark-web pour email ou domaine.
Cible : EMAIL, DOMAIN | clé INTELX_API_KEY requise.
"""
from __future__ import annotations

import asyncio
import os
import time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType

_KEY_ENV = "INTELX_API_KEY"
_BASE    = "https://2.intelx.io"


class IntelXConnector(Connector):
    name         = "intelx_py"
    supports     = {TargetType.EMAIL, TargetType.DOMAIN, TargetType.USERNAME}
    requires_key = True
    rate_limit   = 30
    backend      = "python"

    def _key(self) -> str:
        return os.environ.get(_KEY_ENV, "")

    def is_available(self) -> bool:
        return bool(self._key())

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        key = self._key()
        if not key:
            return ConnectorResult(
                connector=self.name, target=target, success=False,
                error="INTELX_API_KEY not set", elapsed_ms=0,
            )

        headers = {"x-key": key}

        # 1) Lancer la recherche → obtenir search ID
        search_url = f"{_BASE}/intelligent/search"
        body = {
            "term": target.normalized,
            "buckets": [],
            "lookuplevel": 0,
            "maxresults": 20,
            "timeout": 10,
            "datefrom": "",
            "dateto": "",
            "sort": 4,
            "media": 0,
            "terminate": [],
        }
        resp1 = await async_get(
            search_url,
            headers={**headers, "Content-Type": "application/json"},
            timeout=15.0,
        )
        # IntelX search requiert POST — fallback GET si implémentation simple
        # On utilise l'API simplifiée /phonebook/search pour domaine/email
        pb_url = f"{_BASE}/phonebook/search"
        resp1 = await async_get(
            pb_url,
            params={"term": target.normalized, "maxresults": 20, "media": 0, "target": 2},
            headers=headers,
            timeout=15.0,
        )
        elapsed = int((time.monotonic() - t0) * 1000)

        if not resp1["ok"]:
            return ConnectorResult(
                connector=self.name, target=target, success=False,
                error=f"intelx {resp1['status']}: {str(resp1['data'])[:120]}",
                elapsed_ms=elapsed,
            )

        data = resp1["data"]
        if not isinstance(data, dict):
            return ConnectorResult(
                connector=self.name, target=target, success=True,
                findings=[], elapsed_ms=elapsed,
            )

        findings: list[Finding] = []
        # Phonebook results
        for item in data.get("selectors", []):
            if not isinstance(item, dict):
                continue
            val = item.get("selectorvalue", "")
            stype = item.get("selectortype", 0)
            if not val:
                continue
            findings.append(Finding(
                type="leak_reference",
                source="intelx",
                extracted={
                    "value":         val,
                    "selector_type": stype,
                    "target":        target.normalized,
                    "bucket":        item.get("bucket", ""),
                    "date":          item.get("date", ""),
                },
                confidence=0.75,
            ))

        # Search ID results si présents
        sid = data.get("id", "")
        if sid and not findings:
            await asyncio.sleep(3)
            result_url = f"{_BASE}/intelligent/search/result"
            resp2 = await async_get(
                result_url,
                params={"id": sid, "limit": 20, "offset": 0},
                headers=headers,
                timeout=15.0,
            )
            if resp2["ok"] and isinstance(resp2["data"], dict):
                for rec in resp2["data"].get("records", []):
                    if isinstance(rec, dict):
                        findings.append(Finding(
                            type="leak_record",
                            source="intelx",
                            extracted={
                                "target":  target.normalized,
                                "name":    rec.get("name", ""),
                                "bucket":  rec.get("bucket", ""),
                                "date":    rec.get("date", ""),
                                "size":    rec.get("size", 0),
                                "media":   rec.get("media", 0),
                            },
                            confidence=0.7,
                        ))

        return ConnectorResult(
            connector=self.name, target=target, success=True,
            findings=findings, elapsed_ms=int((time.monotonic()-t0)*1000),
        )


get_registry().register(IntelXConnector())
