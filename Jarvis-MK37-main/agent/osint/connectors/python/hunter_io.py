"""
Hunter.io — découverte d'emails depuis un domaine.
Cibles : DOMAIN | clé HUNTER_KEY requise.
"""
from __future__ import annotations
import os, time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType

_KEY_ENV = "HUNTER_KEY"
_BASE    = "https://api.hunter.io/v2"


class HunterIOConnector(Connector):
    name         = "hunter_io"
    supports     = {TargetType.DOMAIN}
    requires_key = True
    rate_limit   = 25
    backend      = "python"

    def _key(self): return os.environ.get(_KEY_ENV, "")
    def is_available(self): return bool(self._key())

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        key = self._key()
        if not key:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error="HUNTER_KEY not set", elapsed_ms=0)
        resp = await async_get(f"{_BASE}/domain-search",
                               params={"domain": target.normalized, "api_key": key, "limit": 20},
                               timeout=12.0)
        elapsed = int((time.monotonic() - t0) * 1000)
        if not resp["ok"]:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error=f"hunter {resp['status']}: {str(resp['data'])[:120]}",
                                   elapsed_ms=elapsed)
        d = resp["data"]
        data = d.get("data", {}) if isinstance(d, dict) else {}
        findings: list[Finding] = []
        # Organisation summary
        org = Finding(
            type="org_emails",
            source="hunter.io",
            url=f"https://hunter.io/domain-search/{target.normalized}",
            extracted={
                "domain":          target.normalized,
                "organization":    data.get("organization", ""),
                "emails_count":    data.get("emails", [{}]) and len(data.get("emails", [])),
                "pattern":         data.get("pattern", ""),
                "webmail":         data.get("webmail", False),
                "disposable":      data.get("disposable", False),
                "accept_all":      data.get("accept_all", False),
            },
            confidence=0.85,
        )
        findings.append(org)
        for email_obj in data.get("emails", [])[:20]:
            findings.append(Finding(
                type="email_discovered",
                source="hunter.io",
                extracted={
                    "domain":      target.normalized,
                    "email":       email_obj.get("value", ""),
                    "first_name":  email_obj.get("first_name", ""),
                    "last_name":   email_obj.get("last_name", ""),
                    "position":    email_obj.get("position", ""),
                    "confidence":  email_obj.get("confidence", 0),
                    "linkedin":    email_obj.get("linkedin", ""),
                    "sources":     [s.get("uri", "") for s in email_obj.get("sources", [])[:3]],
                },
                confidence=email_obj.get("confidence", 50) / 100,
            ))
        return ConnectorResult(connector=self.name, target=target, success=True,
                               findings=findings, elapsed_ms=elapsed)


get_registry().register(HunterIOConnector())
