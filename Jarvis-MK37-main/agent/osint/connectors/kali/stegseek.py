"""stegseek wrapper — détection stéganographie LSB rapide."""
from __future__ import annotations

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class StegseekConnector(Connector):
    name = "stegseek"
    supports = {TargetType.IMAGE}
    backend = "kali"
    requires_key = False
    rate_limit = 60

    def is_available(self) -> bool:
        return get_runner().is_tool_available("stegseek")

    async def query(self, target: Target):
        runner = get_runner()
        # Crack avec wordlist standard rockyou (si dispo) ou skip
        result = await runner.run(
            ["stegseek", "--crack", target.normalized,
             "/usr/share/wordlists/rockyou.txt", "/tmp/steg_extract.bin"],
            timeout=120,
        )
        # stegseek retourne 0 si trouvé, autre code sinon
        findings: list[Finding] = []
        if "Found passphrase" in (result.stdout + result.stderr):
            # Extract passphrase from output
            for line in result.stdout.splitlines() + result.stderr.splitlines():
                if "Found passphrase:" in line:
                    passphrase = line.split(":", 1)[1].strip().strip('"')
                    findings.append(Finding(
                        type="stega_hidden_data",
                        source="stegseek",
                        extracted={"passphrase": passphrase,
                                   "extracted_to": "/tmp/steg_extract.bin",
                                   "image": target.normalized},
                        confidence=0.99,
                    ))
                    break
        elif "no embedded data" in (result.stdout + result.stderr).lower():
            return ok(self.name, target, [], result.elapsed_ms)
        return ok(self.name, target, findings, result.elapsed_ms,
                  raw={"stdout": (result.stdout or "")[:500]})


get_registry().register(StegseekConnector())
