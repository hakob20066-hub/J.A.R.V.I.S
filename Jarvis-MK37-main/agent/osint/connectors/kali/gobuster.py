"""gobuster wrapper — alternative ffuf, dir mode."""
from __future__ import annotations
import re

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


WORDLIST = "/usr/share/wordlists/dirb/common.txt"
RESULT_LINE = re.compile(r"^(/[^\s]+)\s+\(Status:\s+(\d+)\)\s+\[Size:\s+(\d+)\]")


class GobusterConnector(Connector):
    name = "gobuster"
    supports = {TargetType.DOMAIN}
    backend = "kali"
    requires_key = False
    rate_limit = 12

    def is_available(self) -> bool:
        return get_runner().is_tool_available("gobuster")

    async def query(self, target: Target):
        runner = get_runner()
        url = target.normalized if target.normalized.startswith("http") \
              else f"https://{target.normalized}"

        result = await runner.run(
            ["gobuster", "dir", "-u", url, "-w", WORDLIST, "-q",
             "-s", "200,301,302,403", "-t", "20"],
            timeout=180,
        )
        if not result.success and not result.stdout:
            return fail(self.name, target, result.error or "no output", result.elapsed_ms)

        findings: list[Finding] = []
        for m in RESULT_LINE.finditer(result.stdout):
            path, status, size = m.groups()
            findings.append(Finding(
                type="web_path",
                source="gobuster",
                url=url.rstrip("/") + path,
                extracted={"path": path, "status": int(status), "size": int(size),
                           "domain": target.normalized},
                confidence=0.85,
            ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(GobusterConnector())
