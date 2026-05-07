"""googler wrapper — Google search CLI."""
from __future__ import annotations
import json

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class GooglerConnector(Connector):
    name = "googler"
    supports = {TargetType.PERSON_FULL, TargetType.USERNAME, TargetType.PSEUDONYM,
                TargetType.EMAIL, TargetType.DOMAIN, TargetType.PHONE}
    backend = "kali"
    requires_key = False
    rate_limit = 20  # Google rate-limit aggressive

    def is_available(self) -> bool:
        return get_runner().is_tool_available("googler")

    async def query(self, target: Target):
        runner = get_runner()
        result = await runner.run(
            ["googler", "--json", "-n", "20", f'"{target.raw}"'],
            timeout=30,
        )
        if not result.success and not result.stdout:
            return fail(self.name, target, result.error or "no output", result.elapsed_ms)

        findings: list[Finding] = []
        try:
            results = json.loads(result.stdout)
        except json.JSONDecodeError:
            return fail(self.name, target, "JSON parse failed", result.elapsed_ms)

        for r in (results or [])[:20]:
            findings.append(Finding(
                type="search_result",
                source="google",
                url=r.get("url"),
                extracted={
                    "title": r.get("title", ""),
                    "abstract": r.get("abstract", ""),
                    "url": r.get("url"),
                },
                confidence=0.7,
            ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(GooglerConnector())
