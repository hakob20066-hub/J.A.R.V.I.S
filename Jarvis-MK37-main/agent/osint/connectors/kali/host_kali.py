"""host wrapper — basic DNS lookup."""
from __future__ import annotations
import re

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


HOST_OUT = re.compile(r"^([\w.\-]+) has (?:address|IPv6 address|alias for) (.+)$")
HOST_MX  = re.compile(r"^([\w.\-]+) mail is handled by (\d+) (.+)$")


class HostConnector(Connector):
    name = "host"
    supports = {TargetType.DOMAIN, TargetType.IP}
    backend = "kali"
    requires_key = False
    rate_limit = 600

    def is_available(self) -> bool:
        return get_runner().is_tool_available("host")

    async def query(self, target: Target):
        runner = get_runner()
        result = await runner.run(["host", "-W", "3", target.normalized], timeout=15)
        if not result.success and not result.stdout:
            return fail(self.name, target, result.error or "no output", result.elapsed_ms)

        findings: list[Finding] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            m = HOST_OUT.match(line)
            if m:
                findings.append(Finding(
                    type="dns_record",
                    source="host",
                    extracted={"host": m.group(1), "value": m.group(2)},
                    confidence=0.95,
                ))
                continue
            m = HOST_MX.match(line)
            if m:
                findings.append(Finding(
                    type="dns_record",
                    source="host",
                    extracted={"host": m.group(1), "type": "MX",
                               "priority": int(m.group(2)), "value": m.group(3)},
                    confidence=0.95,
                ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(HostConnector())
