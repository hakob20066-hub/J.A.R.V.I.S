"""Holehe wrapper — email → comptes existants sur services."""
from __future__ import annotations
import json

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class HoleheConnector(Connector):
    name = "holehe"
    supports = {TargetType.EMAIL}
    backend = "kali"
    requires_key = False
    rate_limit = 60

    def is_available(self) -> bool:
        return get_runner().is_tool_available("holehe")

    async def query(self, target: Target):
        runner = get_runner()
        result = await runner.run(
            ["holehe", "--only-used", "--no-color", target.normalized],
            timeout=120,
        )
        if not result.success and not result.stdout:
            return fail(self.name, target, result.error or "no output", result.elapsed_ms)

        findings: list[Finding] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            # Format: [+] adobe.com   ou   [-] notfound.com
            if not line.startswith("[+]"):
                continue
            site = line[3:].strip().split()[0] if len(line) > 3 else ""
            if not site:
                continue
            findings.append(Finding(
                type="account",
                source=site,
                url=f"https://{site}",
                extracted={"email": target.normalized, "site": site, "exists": True},
                confidence=0.85,
            ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(HoleheConnector())
