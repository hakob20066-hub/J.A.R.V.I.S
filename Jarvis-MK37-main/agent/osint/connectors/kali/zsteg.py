"""zsteg wrapper — stéganalyse PNG/BMP."""
from __future__ import annotations

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class ZstegConnector(Connector):
    name = "zsteg"
    supports = {TargetType.IMAGE}
    backend = "kali"
    requires_key = False
    rate_limit = 60

    def is_available(self) -> bool:
        return get_runner().is_tool_available("zsteg")

    async def query(self, target: Target):
        norm = target.normalized.lower()
        if not (norm.endswith(".png") or norm.endswith(".bmp")):
            return fail(self.name, target, "zsteg supports PNG/BMP only", 0)

        runner = get_runner()
        result = await runner.run(["zsteg", "-a", target.normalized], timeout=60)
        if not result.success and not result.stdout:
            return fail(self.name, target, result.error or "no output", result.elapsed_ms)

        findings: list[Finding] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            # zsteg lines look like: "b1,r,lsb,xy .. text: \"hello\""
            if "text:" in line or "ascii:" in line.lower() or "file:" in line.lower():
                findings.append(Finding(
                    type="stega_lsb",
                    source="zsteg",
                    extracted={"raw": line[:200], "image": target.normalized},
                    confidence=0.7,
                ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(ZstegConnector())
