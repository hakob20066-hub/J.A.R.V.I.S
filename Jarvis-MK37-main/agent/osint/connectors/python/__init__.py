"""
Connecteurs OSINT Python natifs — auto-enregistrement au import.
Chaque module appelle get_registry().register() à son chargement.
Session 4 : 11 | Session 5 : +15 | Session 6 : +1 person_search
"""
from agent.osint.connectors.python import (  # noqa: F401
    # Session 4
    crtsh, hibp, ipapi, whois_py, dns_py,
    gravatar_py, wayback_cdx, intelx_py, shodan_py,
    hackertarget_py, emailrep_py,
    # Session 5
    virustotal_py, urlscan_py, abuseipdb_py, hunter_io, github_py,
    dehashed_py, otx_py, bgpview_py, securitytrails_py, leakcheck_py,
    numverify_py, fullcontact_py, pulsedive_py, censys_py, builtwith_py,
    # Session 6
    person_search_py, email_pivot_py,
)

__all__ = [
    # S4
    "crtsh", "hibp", "ipapi", "whois_py", "dns_py",
    "gravatar_py", "wayback_cdx", "intelx_py", "shodan_py",
    "hackertarget_py", "emailrep_py",
    # S5
    "virustotal_py", "urlscan_py", "abuseipdb_py", "hunter_io", "github_py",
    "dehashed_py", "otx_py", "bgpview_py", "securitytrails_py", "leakcheck_py",
    "numverify_py", "fullcontact_py", "pulsedive_py", "censys_py", "builtwith_py",
    # S6
    "person_search_py", "email_pivot_py",
]
