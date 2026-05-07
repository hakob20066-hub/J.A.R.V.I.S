"""Photon wrapper — web crawler (URLs, emails, files, secrets)."""
from __future__ import annotations
import json

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


class PhotonConnector(Connector):
    name = "photon"
    supports = {TargetType.DOMAIN}
    backend = "kali"
    requires_key = False
    rate_limit = 30

    def is_available(self) -> bool:
        return get_runner().is_tool_available("photon")

    async def query(self, target: Target):
        runner = get_runner()
        url = target.normalized if target.normalized.startswith("http") \
              else f"https://{target.normalized}"
        out_dir = f"/tmp/photon_{target.hash()}"
        result = await runner.run(
            ["photon", "-u", url, "-o", out_dir, "--threads", "3", "--level", "2"],
            timeout=300,
        )
        if not result.success and not result.stdout:
            return fail(self.name, target, result.error or "no output", result.elapsed_ms)

        findings: list[Finding] = []
        # Photon écrit ses résultats dans des .txt + JSON
        for fname in ("emails.txt", "subdomains.txt", "files.txt", "external_files.txt"):
            cat = await runner.run(["cat", f"{out_dir}/{fname}"], timeout=10)
            if not cat.success:
                continue
            ftype = {"emails.txt": "email", "subdomains.txt": "subdomain",
                     "files.txt": "file", "external_files.txt": "external_file"}[fname]
            for line in cat.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                findings.append(Finding(
                    type=ftype,
                    source="photon",
                    extracted={ftype: line, "domain": target.normalized},
                    confidence=0.8,
                ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(PhotonConnector())
