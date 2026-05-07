"""dnsrecon wrapper — DNS recon complémentaire à dnsenum."""
from __future__ import annotations
import json

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class DnsreconConnector(Connector):
    name = "dnsrecon"
    supports = {TargetType.DOMAIN}
    backend = "kali"
    requires_key = False
    rate_limit = 30

    def is_available(self) -> bool:
        return get_runner().is_tool_available("dnsrecon")

    async def query(self, target: Target):
        runner = get_runner()
        out_path = f"/tmp/dnsrecon_{target.hash()}.json"
        result = await runner.run(
            ["dnsrecon", "-d", target.normalized, "-t", "std",
             "--json", out_path],
            timeout=120,
        )
        cat = await runner.run(["cat", out_path], timeout=5)
        if not cat.success:
            return fail(self.name, target, "dnsrecon no output", result.elapsed_ms)

        findings: list[Finding] = []
        try:
            data = json.loads(cat.stdout)
            entries = data if isinstance(data, list) else data.get("results", [])
            for r in entries[:200]:
                rtype = r.get("type") or "DNS"
                name = r.get("name") or r.get("address") or ""
                if not name:
                    continue
                findings.append(Finding(
                    type="dns_record",
                    source="dnsrecon",
                    extracted={"name": name,
                               "type": rtype,
                               "address": r.get("address"),
                               "target": r.get("target"),
                               "domain": target.normalized},
                    confidence=0.92,
                ))
        except json.JSONDecodeError:
            pass
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(DnsreconConnector())
