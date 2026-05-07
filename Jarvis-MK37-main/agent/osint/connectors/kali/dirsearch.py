"""dirsearch wrapper — Python-based dir bruteforce."""
from __future__ import annotations
import json

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class DirsearchConnector(Connector):
    name = "dirsearch"
    supports = {TargetType.DOMAIN}
    backend = "kali"
    requires_key = False
    rate_limit = 12

    def is_available(self) -> bool:
        return get_runner().is_tool_available("dirsearch")

    async def query(self, target: Target):
        runner = get_runner()
        url = target.normalized if target.normalized.startswith("http") \
              else f"https://{target.normalized}"

        result = await runner.run(
            ["dirsearch", "-u", url, "-q", "--format=json",
             "-o", "/tmp/dirsearch.json", "-t", "20"],
            timeout=180,
        )
        cat = await runner.run(["cat", "/tmp/dirsearch.json"], timeout=5)
        if not cat.success:
            return fail(self.name, target, "dirsearch no output", result.elapsed_ms)

        findings: list[Finding] = []
        try:
            data = json.loads(cat.stdout)
            results = data.get("results", []) if isinstance(data, dict) else (data or [])
            for r in results[:100]:
                findings.append(Finding(
                    type="web_path",
                    source="dirsearch",
                    url=r.get("url"),
                    extracted={"path": r.get("path") or r.get("url"),
                               "status": r.get("status"),
                               "size": r.get("content-length"),
                               "domain": target.normalized},
                    confidence=0.85,
                ))
        except json.JSONDecodeError:
            pass
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(DirsearchConnector())
