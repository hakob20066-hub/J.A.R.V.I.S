"""ffuf wrapper — web fuzzing dirs/files."""
from __future__ import annotations
import json

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


# Wordlist Kali standard
WORDLIST = "/usr/share/wordlists/dirb/common.txt"


class FfufConnector(Connector):
    name = "ffuf"
    supports = {TargetType.DOMAIN}
    backend = "kali"
    requires_key = False
    rate_limit = 12

    def is_available(self) -> bool:
        return get_runner().is_tool_available("ffuf")

    async def query(self, target: Target):
        runner = get_runner()
        url = target.normalized if target.normalized.startswith("http") \
              else f"https://{target.normalized}"
        url = url.rstrip("/") + "/FUZZ"

        result = await runner.run(
            ["ffuf", "-u", url, "-w", WORDLIST, "-mc", "200,301,302,403",
             "-of", "json", "-o", "/tmp/ffuf.json", "-t", "20", "-s"],
            timeout=180,
        )
        cat = await runner.run(["cat", "/tmp/ffuf.json"], timeout=5)
        if not cat.success:
            return fail(self.name, target, "ffuf no output", result.elapsed_ms)

        findings: list[Finding] = []
        try:
            data = json.loads(cat.stdout)
            for r in (data.get("results", []) or [])[:100]:
                findings.append(Finding(
                    type="web_path",
                    source="ffuf",
                    url=r.get("url"),
                    extracted={"path": r.get("input", {}).get("FUZZ"),
                               "status": r.get("status"),
                               "length": r.get("length"),
                               "domain": target.normalized},
                    confidence=0.85,
                ))
        except json.JSONDecodeError:
            pass
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(FfufConnector())
