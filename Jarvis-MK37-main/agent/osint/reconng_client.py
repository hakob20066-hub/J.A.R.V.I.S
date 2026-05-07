"""
recon-ng client — workspace + script.rc CLI.

Voir [[14-Phases/phase7.6-reconng-client]].
"""
from __future__ import annotations

import json
import re
import tempfile
import time
from pathlib import Path
from typing import Optional

from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


# Modules clés par type cible
RECONNG_MODULES = {
    TargetType.DOMAIN: [
        "recon/domains-hosts/builtwith",
        "recon/domains-hosts/hackertarget",
        "recon/domains-contacts/whois_pocs",
    ],
    TargetType.EMAIL: [
        "recon/contacts-credentials/hibp_breach",
        "recon/contacts-domains/migrate_contacts",
    ],
    TargetType.PERSON_FULL: [
        "recon/contacts-credentials/hibp_breach",
        "recon/profiles-profiles/profiler",
    ],
}


class ReconNgClient:
    """Wrapper recon-ng via script.rc."""

    def __init__(self):
        self._workspace_prefix = "jarvis_"

    def _build_rc(self, modules: list[str], options: dict) -> str:
        lines = []
        for mod in modules:
            lines.append(f"modules load {mod}")
            for k, v in options.items():
                lines.append(f"options set {k.upper()} {v}")
            lines.append("run")
            lines.append("back")
        lines.append("exit")
        return "\n".join(lines)

    async def run_recon(self, target: Target, modules: Optional[list[str]] = None,
                        timeout: int = 180) -> dict:
        """
        Exécute recon-ng dans un workspace dédié, retourne les rows extraites.
        """
        runner = get_runner()
        if not runner.is_tool_available("recon-ng"):
            return {"success": False, "error": "recon-ng not available", "rows": []}

        modules = modules or RECONNG_MODULES.get(target.type, [])
        if not modules:
            return {"success": True, "rows": [], "modules_run": []}

        opt_key = "DOMAIN" if target.type == TargetType.DOMAIN else "SOURCE"
        rc_script = self._build_rc(modules, {opt_key: target.normalized})

        rc_path = f"/tmp/reconng_{target.hash()}.rc"
        await runner.run(["sh", "-c", f"cat > {rc_path} <<'EOF'\n{rc_script}\nEOF"],
                         timeout=5)

        workspace = f"{self._workspace_prefix}{target.hash()}"
        result = await runner.run(
            ["recon-ng", "-w", workspace, "-r", rc_path],
            timeout=timeout,
        )
        # Cleanup workspace ? on garde pour debug
        return {
            "success":     result.success,
            "stdout":      result.stdout[:5000],
            "stderr":      result.stderr[:1000] if result.stderr else "",
            "modules_run": modules,
            "rows":        self._parse_stdout(result.stdout),
            "elapsed_ms":  result.elapsed_ms,
        }

    @staticmethod
    def _parse_stdout(stdout: str) -> list[dict]:
        """Extrait lignes intéressantes (URLs, emails, domaines découverts)."""
        rows = []
        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("[*]") and " => " in line:
                # ex: [*] [host] sub.example.com => 1.2.3.4
                parts = line[3:].strip().split(" => ", 1)
                if len(parts) == 2:
                    rows.append({"key": parts[0].strip(), "value": parts[1].strip()})
        return rows


class ReconNgConnector(Connector):
    name = "recon-ng"
    supports = {TargetType.DOMAIN, TargetType.EMAIL, TargetType.PERSON_FULL}
    backend = "kali"
    requires_key = False
    rate_limit = 20

    def __init__(self):
        self.client = ReconNgClient()

    def is_available(self) -> bool:
        return get_runner().is_tool_available("recon-ng")

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.perf_counter()
        result = await self.client.run_recon(target)
        elapsed_ms = result.get("elapsed_ms", int((time.perf_counter() - t0) * 1000))

        if not result.get("success"):
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   findings=[], elapsed_ms=elapsed_ms,
                                   error=result.get("error", "recon-ng failed"))

        findings = []
        for row in result.get("rows", []):
            findings.append(Finding(
                type="reconng_record",
                source="recon-ng",
                extracted={"key": row["key"], "value": row["value"],
                           "target": target.normalized},
                confidence=0.85,
            ))
        return ConnectorResult(connector=self.name, target=target, success=True,
                               findings=findings, elapsed_ms=elapsed_ms,
                               raw={"modules": result.get("modules_run", [])})


get_registry().register(ReconNgConnector())
