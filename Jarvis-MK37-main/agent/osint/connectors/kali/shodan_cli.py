"""shodan CLI wrapper — host fingerprint via Shodan API."""
from __future__ import annotations
import json

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class ShodanCliConnector(Connector):
    name = "shodan_cli"
    supports = {TargetType.IP, TargetType.DOMAIN}
    backend = "kali"
    requires_key = True   # `shodan init <key>` doit avoir été fait
    rate_limit = 60

    def is_available(self) -> bool:
        return get_runner().is_tool_available("shodan")

    async def query(self, target: Target):
        runner = get_runner()
        if target.type == TargetType.DOMAIN:
            cmd = ["shodan", "domain", target.normalized]
        else:
            cmd = ["shodan", "host", target.normalized]

        result = await runner.run(cmd, timeout=30)
        if not result.success and not result.stdout:
            return fail(self.name, target, result.error or "no output", result.elapsed_ms)

        findings: list[Finding] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "+")):
                continue
            findings.append(Finding(
                type="shodan_record",
                source="shodan",
                extracted={"raw_line": line, "target": target.normalized},
                confidence=0.85,
            ))
        return ok(self.name, target, findings, result.elapsed_ms,
                  raw={"stdout": result.stdout[:2000]})


get_registry().register(ShodanCliConnector())
