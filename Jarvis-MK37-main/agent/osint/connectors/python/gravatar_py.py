"""
Gravatar — vérifie l'existence d'un compte Gravatar pour un email.
Cible : EMAIL | sans clé API.
"""
from __future__ import annotations

import hashlib
import time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_head
from agent.osint.target import Target, TargetType


def _gravatar_hash(email: str) -> str:
    return hashlib.md5(email.strip().lower().encode()).hexdigest()


class GravatarPyConnector(Connector):
    name         = "gravatar_py"
    supports     = {TargetType.EMAIL}
    requires_key = False
    rate_limit   = 60
    backend      = "python"

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        email = target.normalized
        h = _gravatar_hash(email)
        url = f"https://www.gravatar.com/avatar/{h}?d=404"
        profile_url = f"https://gravatar.com/{h}"

        resp = await async_head(url, timeout=6.0)
        elapsed = int((time.monotonic() - t0) * 1000)

        if resp["status"] == 200:
            finding = Finding(
                type="account",
                source="gravatar",
                url=profile_url,
                extracted={
                    "email": email,
                    "gravatar_hash": h,
                    "profile_url": profile_url,
                    "avatar_url": f"https://www.gravatar.com/avatar/{h}",
                },
                confidence=0.85,
            )
            return ConnectorResult(
                connector=self.name, target=target, success=True,
                findings=[finding], elapsed_ms=elapsed,
            )

        return ConnectorResult(
            connector=self.name, target=target, success=True,
            findings=[], elapsed_ms=elapsed,
        )


get_registry().register(GravatarPyConnector())
