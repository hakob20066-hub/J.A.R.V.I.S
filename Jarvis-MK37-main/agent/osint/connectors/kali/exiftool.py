"""exiftool wrapper — image/document metadata extraction."""
from __future__ import annotations
import json

from agent.osint.connectors.base import Connector, Finding, get_registry
from agent.osint.connectors.kali._helpers import fail, ok
from agent.osint.kali_runner import get_runner
from agent.osint.target import Target, TargetType


# Champs sensibles pour OSINT
SENSITIVE_FIELDS = {
    "GPSPosition", "GPSLatitude", "GPSLongitude", "GPSAltitude",
    "DateTimeOriginal", "CreateDate", "ModifyDate",
    "Make", "Model", "Software", "SerialNumber", "LensModel",
    "Author", "Creator", "Copyright", "OwnerName", "Artist",
    "DeviceManufacturer", "DeviceModel",
}


class ExiftoolConnector(Connector):
    name = "exiftool"
    supports = {TargetType.IMAGE}
    backend = "kali"
    requires_key = False
    rate_limit = 600

    def is_available(self) -> bool:
        return get_runner().is_tool_available("exiftool")

    async def query(self, target: Target):
        runner = get_runner()
        result = await runner.run(
            ["exiftool", "-json", "-n", "-coordFormat", "%.6f",
             target.normalized],
            timeout=60,
        )
        if not result.success and not result.stdout:
            return fail(self.name, target, result.error or "no output", result.elapsed_ms)

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return fail(self.name, target, "JSON parse failed", result.elapsed_ms)

        if not data or not isinstance(data, list):
            return ok(self.name, target, [], result.elapsed_ms)

        meta = data[0]
        findings: list[Finding] = []

        # 1) GPS si présent → Finding séparé high-confidence
        if "GPSLatitude" in meta and "GPSLongitude" in meta:
            findings.append(Finding(
                type="exif_gps",
                source="exiftool",
                extracted={
                    "latitude": meta.get("GPSLatitude"),
                    "longitude": meta.get("GPSLongitude"),
                    "altitude": meta.get("GPSAltitude"),
                    "datetime": meta.get("DateTimeOriginal"),
                },
                confidence=0.99,
            ))

        # 2) Champs sensibles
        sensitive = {k: v for k, v in meta.items() if k in SENSITIVE_FIELDS}
        if sensitive:
            findings.append(Finding(
                type="exif_metadata",
                source="exiftool",
                extracted=sensitive,
                confidence=0.95,
            ))
        return ok(self.name, target, findings, result.elapsed_ms)


get_registry().register(ExiftoolConnector())
