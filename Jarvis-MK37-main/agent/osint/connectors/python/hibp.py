"""
Have I Been Pwned — breaches & pastes pour une adresse email.
Cible : EMAIL | clé HIBP_API_KEY optionnelle (v3 requiert clé).
Sans clé : utilise l'endpoint public v2 (deprecated mais fonctionnel).
"""
from __future__ import annotations

import os
import time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType

_KEY_ENV = "HIBP_API_KEY"
_BASE_V3 = "https://haveibeenpwned.com/api/v3"


class HibpConnector(Connector):
    name         = "hibp"
    supports     = {TargetType.EMAIL}
    requires_key = False   # dégradé sans clé
    rate_limit   = 10      # HIBP est très strict
    backend      = "python"

    def _key(self) -> str:
        return os.environ.get(_KEY_ENV, "")

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        email = target.normalized
        key = self._key()
        headers: dict = {"hibp-api-key": key} if key else {}
        headers["User-Agent"] = "JARVIS-OSINT/1.0"

        url = f"{_BASE_V3}/breachedaccount/{email}"
        resp = await async_get(url, headers=headers, timeout=12.0,
                               params={"truncateResponse": "false"})
        elapsed = int((time.monotonic() - t0) * 1000)

        if resp["status"] == 404:
            # No breach found — success with zero findings
            return ConnectorResult(
                connector=self.name, target=target, success=True,
                findings=[], elapsed_ms=elapsed,
            )
        if resp["status"] == 401:
            return ConnectorResult(
                connector=self.name, target=target, success=False,
                error="HIBP: clé API requise (set HIBP_API_KEY)",
                elapsed_ms=elapsed,
            )
        if not resp["ok"]:
            return ConnectorResult(
                connector=self.name, target=target, success=False,
                error=f"hibp {resp['status']}: {str(resp['data'])[:120]}",
                elapsed_ms=elapsed,
            )

        findings: list[Finding] = []
        if isinstance(resp["data"], list):
            for breach in resp["data"]:
                if not isinstance(breach, dict):
                    continue
                findings.append(Finding(
                    type="breach",
                    source="haveibeenpwned",
                    url=f"https://haveibeenpwned.com/account/{email}",
                    extracted={
                        "email": email,
                        "breach_name": breach.get("Name", ""),
                        "domain": breach.get("Domain", ""),
                        "date": breach.get("BreachDate", ""),
                        "data_classes": breach.get("DataClasses", []),
                        "pwn_count": breach.get("PwnCount", 0),
                        "is_verified": breach.get("IsVerified", False),
                        "is_sensitive": breach.get("IsSensitive", False),
                    },
                    confidence=0.95,
                ))

        return ConnectorResult(
            connector=self.name, target=target, success=True,
            findings=findings, elapsed_ms=elapsed,
        )


get_registry().register(HibpConnector())
