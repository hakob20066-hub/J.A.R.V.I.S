"""dig wrapper — DNS query A/AAAA/MX/TXT/NS."""
from __future__ import annotations

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


DIG_RECORDS = ["A", "AAAA", "MX", "TXT", "NS", "SOA", "CNAME"]


class DigConnector(Connector):
    name = "dig"
    supports = {TargetType.DOMAIN}
    backend = "kali"
    requires_key = False
    rate_limit = 600

    def is_available(self) -> bool:
        return get_runner().is_tool_available("dig")

    async def query(self, target: Target):
        runner = get_runner()
        findings: list[Finding] = []
        total_ms = 0

        for rtype in DIG_RECORDS:
            result = await runner.run(
                ["dig", "+short", "+time=3", "+tries=1", target.normalized, rtype],
                timeout=10,
            )
            total_ms += result.elapsed_ms
            if not result.success or not result.stdout.strip():
                continue
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                findings.append(Finding(
                    type="dns_record",
                    source="dig",
                    extracted={"host": target.normalized, "type": rtype, "value": line},
                    confidence=0.98,
                ))
        if not findings:
            return fail(self.name, target, "no DNS records resolved", total_ms)
        return ok(self.name, target, findings, total_ms)


get_registry().register(DigConnector())
