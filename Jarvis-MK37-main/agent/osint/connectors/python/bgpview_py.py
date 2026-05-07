"""
BGPView — ASN, préfixes, pairs pour une IP ou un ASN.
Cibles : IP | sans clé API.
"""
from __future__ import annotations
import time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType

_BASE = "https://api.bgpview.io"


class BGPViewConnector(Connector):
    name         = "bgpview_py"
    supports     = {TargetType.IP}
    requires_key = False
    rate_limit   = 45
    backend      = "python"

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        resp = await async_get(f"{_BASE}/ip/{target.normalized}", timeout=10.0)
        elapsed = int((time.monotonic() - t0) * 1000)
        if not resp["ok"]:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error=f"bgpview {resp['status']}: {str(resp['data'])[:120]}",
                                   elapsed_ms=elapsed)
        d = resp["data"]
        data = d.get("data", {}) if isinstance(d, dict) else {}
        prefixes = data.get("prefixes", [])
        findings: list[Finding] = []
        for prefix in prefixes[:10]:
            asn_info = prefix.get("asn", {})
            findings.append(Finding(
                type="bgp_prefix",
                source="bgpview",
                url=f"https://bgpview.io/ip/{target.normalized}",
                extracted={
                    "ip":           target.normalized,
                    "prefix":       prefix.get("prefix", ""),
                    "asn":          asn_info.get("asn", ""),
                    "asn_name":     asn_info.get("name", ""),
                    "asn_country":  asn_info.get("country_code", ""),
                    "description":  asn_info.get("description", ""),
                    "prefix_name":  prefix.get("name", ""),
                    "rir_alloc":    prefix.get("rir_allocation", {}).get("rir_name", ""),
                },
                confidence=0.9,
            ))
        if not findings:
            # Toujours retourner au moins l'info RIR si dispo
            rir = data.get("rir_allocation", {})
            if rir:
                findings.append(Finding(
                    type="bgp_prefix",
                    source="bgpview",
                    extracted={"ip": target.normalized, "rir": rir.get("rir_name", ""),
                               "allocation": rir.get("prefix", ""),
                               "date_allocated": rir.get("date_allocated", "")},
                    confidence=0.8,
                ))
        return ConnectorResult(connector=self.name, target=target, success=True,
                               findings=findings, elapsed_ms=elapsed)


get_registry().register(BGPViewConnector())
