"""theHarvester wrapper — emails/subdomains/hosts harvesting."""
from __future__ import annotations
import json

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok, parse_emails, parse_domains
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class TheHarvesterConnector(Connector):
    name = "theHarvester"
    supports = {TargetType.DOMAIN}
    backend = "kali"
    requires_key = False
    rate_limit = 30  # search engines rate-limit

    def is_available(self) -> bool:
        return get_runner().is_tool_available("theHarvester")

    async def query(self, target: Target):
        runner = get_runner()
        result = await runner.run(
            ["theHarvester", "-d", target.normalized,
             "-b", "duckduckgo,crtsh,bing,otx",
             "-l", "200", "-f", "/tmp/theh.json"],
            timeout=300,
        )
        if not result.success and not result.stdout:
            return fail(self.name, target, result.error or "no output", result.elapsed_ms)

        findings: list[Finding] = []
        # Parse JSON file généré (ou stdout)
        emails = []
        hosts = []
        try:
            cat = await runner.run(["cat", "/tmp/theh.json"], timeout=10)
            if cat.success:
                data = json.loads(cat.stdout)
                emails = data.get("emails", []) or []
                hosts = data.get("hosts", []) or []
        except Exception:
            pass
        # Fallback : parse stdout
        if not emails:
            emails = parse_emails(result.stdout)
        if not hosts:
            hosts = parse_domains(result.stdout)

        for email in emails:
            findings.append(Finding(
                type="email",
                source="theHarvester",
                extracted={"email": email, "domain": target.normalized},
                confidence=0.85,
            ))
        for h in hosts:
            findings.append(Finding(
                type="subdomain",
                source="theHarvester",
                extracted={"subdomain": h, "domain": target.normalized},
                confidence=0.8,
            ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(TheHarvesterConnector())
