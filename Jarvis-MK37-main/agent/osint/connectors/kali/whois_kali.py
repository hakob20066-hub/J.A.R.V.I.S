"""whois wrapper — domain registration info."""
from __future__ import annotations
import re

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


WHOIS_FIELDS = {
    "registrar":           re.compile(r"(?im)^\s*Registrar:\s*(.+)$"),
    "creation_date":       re.compile(r"(?im)^\s*Creation Date:\s*(.+)$"),
    "expiry_date":         re.compile(r"(?im)^\s*(?:Registry|Expiry) Expir(?:y|ation) Date:\s*(.+)$"),
    "registrant_org":      re.compile(r"(?im)^\s*Registrant Organization:\s*(.+)$"),
    "registrant_country":  re.compile(r"(?im)^\s*Registrant Country:\s*(.+)$"),
    "name_servers":        re.compile(r"(?im)^\s*Name Server:\s*(.+)$"),
}


class WhoisConnector(Connector):
    name = "whois"
    supports = {TargetType.DOMAIN, TargetType.IP}
    backend = "kali"
    requires_key = False
    rate_limit = 120

    def is_available(self) -> bool:
        return get_runner().is_tool_available("whois")

    async def query(self, target: Target):
        runner = get_runner()
        result = await runner.run(["whois", target.normalized], timeout=20)
        if not result.success and not result.stdout:
            return fail(self.name, target, result.error or "no output", result.elapsed_ms)

        extracted: dict = {}
        for key, regex in WHOIS_FIELDS.items():
            matches = [m.strip() for m in regex.findall(result.stdout)]
            if matches:
                extracted[key] = matches if len(matches) > 1 else matches[0]
        if not extracted:
            return ok(self.name, target, [], result.elapsed_ms, raw={"stdout": result.stdout[:500]})

        findings = [Finding(
            type="whois",
            source="whois",
            extracted=extracted,
            confidence=0.95,
        )]
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(WhoisConnector())
