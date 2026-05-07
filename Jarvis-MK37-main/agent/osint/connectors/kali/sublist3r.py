"""Sublist3r wrapper — subdomain enum."""
from __future__ import annotations

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok, parse_domains
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class Sublist3rConnector(Connector):
    name = "sublist3r"
    supports = {TargetType.DOMAIN}
    backend = "kali"
    requires_key = False
    rate_limit = 30

    def is_available(self) -> bool:
        return get_runner().is_tool_available("sublist3r")

    async def query(self, target: Target):
        runner = get_runner()
        result = await runner.run(
            ["sublist3r", "-d", target.normalized, "-o", "/tmp/sublist3r.txt", "-v"],
            timeout=240,
        )
        if not result.success and not result.stdout:
            return fail(self.name, target, result.error or "no output", result.elapsed_ms)

        # Parse stdout (lines starting with target)
        findings: list[Finding] = []
        seen: set[str] = set()
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith(("[", "-", "=")):
                continue
            for d in parse_domains(line):
                if target.normalized in d and d != target.normalized and d not in seen:
                    seen.add(d)
                    findings.append(Finding(
                        type="subdomain",
                        source="sublist3r",
                        extracted={"subdomain": d, "domain": target.normalized},
                        confidence=0.85,
                    ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(Sublist3rConnector())
