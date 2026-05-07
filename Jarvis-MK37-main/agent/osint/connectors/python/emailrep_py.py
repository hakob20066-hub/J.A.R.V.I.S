"""
emailrep.io — réputation d'une adresse email (spam, breach, deliverable).
Cible : EMAIL | sans clé API pour basic (3 req/h), clé EMAILREP_KEY pour plus.
"""
from __future__ import annotations

import os
import time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType

_KEY_ENV = "EMAILREP_KEY"
_BASE    = "https://emailrep.io"


class EmailRepConnector(Connector):
    name         = "emailrep_py"
    supports     = {TargetType.EMAIL}
    requires_key = False
    rate_limit   = 3    # sans clé : 3/h
    backend      = "python"

    def _key(self) -> str:
        return os.environ.get(_KEY_ENV, "")

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        email = target.normalized
        key = self._key()
        headers: dict = {}
        if key:
            headers["Key"] = key

        resp = await async_get(f"{_BASE}/{email}", headers=headers, timeout=10.0)
        elapsed = int((time.monotonic() - t0) * 1000)

        if resp["status"] == 429:
            return ConnectorResult(
                connector=self.name, target=target, success=False,
                error="emailrep: rate limited (set EMAILREP_KEY)",
                elapsed_ms=elapsed,
            )
        if not resp["ok"]:
            return ConnectorResult(
                connector=self.name, target=target, success=False,
                error=f"emailrep {resp['status']}: {str(resp['data'])[:120]}",
                elapsed_ms=elapsed,
            )

        d = resp["data"]
        if not isinstance(d, dict):
            return ConnectorResult(
                connector=self.name, target=target, success=False,
                error="emailrep: unexpected response", elapsed_ms=elapsed,
            )

        attrs = d.get("details", {}) or {}
        finding = Finding(
            type="email_reputation",
            source="emailrep.io",
            extracted={
                "email":             email,
                "reputation":        d.get("reputation", ""),
                "suspicious":        d.get("suspicious", False),
                "references":        d.get("references", 0),
                "blacklisted":       attrs.get("blacklisted", False),
                "malicious_activity": attrs.get("malicious_activity", False),
                "spam":              attrs.get("spam", False),
                "deliverable":       attrs.get("deliverable", True),
                "free_provider":     attrs.get("free_provider", False),
                "disposable":        attrs.get("disposable", False),
                "first_seen":        attrs.get("first_seen", ""),
                "last_seen":         attrs.get("last_seen", ""),
                "seen_count":        attrs.get("seen_count", 0),
                "profiles":          attrs.get("profiles", []),
            },
            confidence=0.8,
        )
        return ConnectorResult(
            connector=self.name, target=target, success=True,
            findings=[finding], elapsed_ms=elapsed,
        )


get_registry().register(EmailRepConnector())
