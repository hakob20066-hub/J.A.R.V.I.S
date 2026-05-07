"""
Kali wrappers — auto-import + auto-registration.

Tous les modules de ce package s'enregistrent dans le ConnectorRegistry au import.
"""
from agent.osint.connectors.kali import (
    # Session 2
    sherlock, maigret, holehe, theharvester,
    sublist3r, subfinder, amass,
    whois_kali, dnsenum, dig_kali, host_kali, nmap_kali,
    shodan_cli,
    waybackurls, gau, photon, googler,
    exiftool, stegseek, instaloader,
    # Session 3
    gitleaks, trufflehog, zsteg, steghide, fierce,
    ffuf, gobuster, dirsearch,
    twint, osintgram, phoneinfoga, nuclei,
    linkedin2username, dnsrecon, recon_ng_cli,
)

__all__ = [
    "sherlock", "maigret", "holehe", "theharvester",
    "sublist3r", "subfinder", "amass",
    "whois_kali", "dnsenum", "dig_kali", "host_kali", "nmap_kali",
    "shodan_cli",
    "waybackurls", "gau", "photon", "googler",
    "exiftool", "stegseek", "instaloader",
    "gitleaks", "trufflehog", "zsteg", "steghide", "fierce",
    "ffuf", "gobuster", "dirsearch",
    "twint", "osintgram", "phoneinfoga", "nuclei",
    "linkedin2username", "dnsrecon", "recon_ng_cli",
]
