"""steghide wrapper — stéganalyse JPG (passive info only)."""
from __future__ import annotations

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class SteghideConnector(Connector):
    name = "steghide"
    supports = {TargetType.IMAGE}
    backend = "kali"
    requires_key = False
    rate_limit = 60

    def is_available(self) -> bool:
        return get_runner().is_tool_available("steghide")

    async def query(self, target: Target):
        norm = target.normalized.lower()
        if not (norm.endswith(".jpg") or norm.endswith(".jpeg")):
            return fail(self.name, target, "steghide supports JPG only", 0)

        runner = get_runner()
        # info passif (sans extraction)
        result = await runner.run(["steghide", "info", target.normalized,
                                   "--passphrase", ""], timeout=20)
        findings: list[Finding] = []
        if "embedded file" in result.stdout.lower() or "capacity" in result.stdout.lower():
            findings.append(Finding(
                type="stega_jpg_signature",
                source="steghide",
                extracted={"info": result.stdout[:300], "image": target.normalized},
                confidence=0.6,
            ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(SteghideConnector())
