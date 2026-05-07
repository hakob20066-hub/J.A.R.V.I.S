"""phoneinfoga wrapper — phone OSINT."""
from __future__ import annotations
import json
import re

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class PhoneinfogaConnector(Connector):
    name = "phoneinfoga"
    supports = {TargetType.PHONE}
    backend = "kali"
    requires_key = False
    rate_limit = 60

    def is_available(self) -> bool:
        return get_runner().is_tool_available("phoneinfoga")

    async def query(self, target: Target):
        runner = get_runner()
        # phoneinfoga scan -n <number>
        result = await runner.run(
            ["phoneinfoga", "scan", "-n", target.normalized],
            timeout=60,
        )
        if not result.success and not result.stdout:
            return fail(self.name, target, result.error or "no output", result.elapsed_ms)

        findings: list[Finding] = []
        # Parse stdout : country, carrier, line type, etc.
        info = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            m = re.match(r"^([A-Z][a-z][^:]+):\s+(.+)$", line)
            if m:
                k, v = m.group(1).lower().replace(" ", "_"), m.group(2).strip()
                info[k] = v
        if info:
            findings.append(Finding(
                type="phone_info",
                source="phoneinfoga",
                extracted={"phone": target.normalized, **info},
                confidence=0.9,
            ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(PhoneinfogaConnector())
