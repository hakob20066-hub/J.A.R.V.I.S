---
title: Phase 7.6 — 26 connecteurs Python fallback / non-Kali
date: 2026-05-07
tags: [phase7.6, connectors, python, session4, session5]
parent_moc: [[00-MOC/MOC-OSINT]]
---

# Connecteurs Python natifs

Sources qui n'existent pas en Kali ou nécessitent API key cloud.
Fonctionnent sur Windows sans WSL. Dossier : `agent/osint/connectors/python/`.

Auto-enregistrement : import du package → `get_registry().register()` par module.

---

## Base HTTP partagée — `_http.py`

Session httpx async partagée :
- Retry exponentiel ×3 sur 429/503
- Semaphore global 16 requêtes parallèles
- Fallback `requests` sync si httpx absent

```python
resp = await async_get("https://api.example.com", params={"q": "x"}, timeout=10.0)
# → {"ok": True, "status": 200, "data": {...}, "elapsed_ms": 342}
```

---

## Session 4 — 11 connecteurs

| Connecteur | Cibles | Clé | Finding type |
|------------|--------|-----|-------------|
| `crtsh` | DOMAIN | non | `subdomain` |
| `hibp` | EMAIL | opt. `HIBP_API_KEY` | `breach` |
| `ipapi` | IP | non | `geoip` |
| `whois_py` | DOMAIN, IP | non | `whois` |
| `dns_py` | DOMAIN, IP | non | `dns_record` |
| `gravatar_py` | EMAIL | non | `account` |
| `wayback_cdx` | DOMAIN | non | `wayback_snapshot` |
| `intelx_py` | EMAIL, DOMAIN, USERNAME | `INTELX_API_KEY` | `leak_reference` |
| `shodan_py` | IP | `SHODAN_API_KEY` | `host_info`, `open_port` |
| `hackertarget_py` | DOMAIN, IP | non | `dns_record` |
| `emailrep_py` | EMAIL | opt. `EMAILREP_KEY` | `email_reputation` |

---

## Session 5 — 15 connecteurs

| Connecteur | Cibles | Clé(s) | Finding type |
|------------|--------|---------|-------------|
| `virustotal_py` | DOMAIN, IP | `VT_API_KEY` | `reputation` |
| `urlscan_py` | DOMAIN | non | `url_scan` |
| `abuseipdb_py` | IP | `ABUSEIPDB_KEY` | `abuse_report` |
| `hunter_io` | DOMAIN | `HUNTER_KEY` | `email_discovery` |
| `github_py` | USERNAME | opt. `GITHUB_TOKEN` | `social_profile` |
| `dehashed_py` | EMAIL, USERNAME | `DEHASHED_EMAIL`+`DEHASHED_KEY` | `credential_leak` |
| `otx_py` | DOMAIN, IP | opt. `OTX_KEY` | `threat_intel` |
| `bgpview_py` | IP | non | `bgp_info` |
| `securitytrails_py` | DOMAIN | `ST_API_KEY` | `subdomain`, `dns_history` |
| `leakcheck_py` | EMAIL | `LEAKCHECK_KEY` | `credential_leak` |
| `numverify_py` | PHONE | `NUMVERIFY_KEY` | `phone_info` |
| `fullcontact_py` | EMAIL | `FC_API_KEY` | `person_profile` |
| `pulsedive_py` | DOMAIN, IP | opt. `PD_KEY` | `threat_intel` |
| `censys_py` | IP | `CENSYS_API_ID`+`CENSYS_API_SECRET` | `host_info` |
| `builtwith_py` | DOMAIN | `BW_API_KEY` | `tech_stack` |

---

## Variables d'environnement

```bash
# Session 4
HIBP_API_KEY=  INTELX_API_KEY=  SHODAN_API_KEY=  EMAILREP_KEY=
# Session 5
VT_API_KEY=  ABUSEIPDB_KEY=  HUNTER_KEY=  GITHUB_TOKEN=
DEHASHED_EMAIL=  DEHASHED_KEY=  OTX_KEY=  ST_API_KEY=
LEAKCHECK_KEY=  NUMVERIFY_KEY=  FC_API_KEY=  PD_KEY=
CENSYS_API_ID=  CENSYS_API_SECRET=  BW_API_KEY=
```

---

## Tests

```bash
python tests/test_session4_osint.py   # 55/55
python tests/test_session5_osint.py   # 39/39
python -m pytest tests/ -q            # 304/304
```

## Liens

- [[phase7.6-connectors-kali]]
- [[phase7.6-analyzers]]
- [[phase7.6-session4-complete]]
- [[phase7.6-session5-complete]]
