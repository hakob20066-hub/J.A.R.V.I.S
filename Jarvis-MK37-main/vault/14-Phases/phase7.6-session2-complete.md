---
title: Phase 7.6 — Session 2 ✅ DONE (20 wrappers Kali core)
date: 2026-05-07
tags: [phase7.6, osint, session2, livraison, done, kali]
parent_moc: [[00-MOC/MOC-Phases]]
---

# Session 2 — 20 wrappers Kali core

**Statut** : ✅ DONE
**Tests** : **190/190 PASS** (130 base + 47 OSINT core + 13 connectors Kali)

## 📦 20 wrappers livrés

| # | Connector | Cibles supportées | Outil Kali |
|---|---|---|---|
| 1 | `sherlock` | username, pseudonym, instagram_handle | sherlock |
| 2 | `maigret` | username, pseudonym, instagram_handle | maigret (3000+ sites) |
| 3 | `holehe` | email | holehe |
| 4 | `theHarvester` | domain | theHarvester |
| 5 | `sublist3r` | domain | sublist3r |
| 6 | `subfinder` | domain | subfinder (ProjectDiscovery) |
| 7 | `amass` | domain | amass (passive) |
| 8 | `whois` | domain, ip | whois |
| 9 | `dnsenum` | domain | dnsenum |
| 10 | `dig` | domain | dig (7 record types) |
| 11 | `host` | domain, ip | host |
| 12 | `nmap` | ip, domain | nmap (-F -sV light) |
| 13 | `shodan_cli` | ip, domain | shodan CLI |
| 14 | `waybackurls` | domain | waybackurls |
| 15 | `gau` | domain | gau (Wayback+OTX+CC) |
| 16 | `photon` | domain | photon (web crawler) |
| 17 | `googler` | person, username, email, domain, phone | googler |
| 18 | `exiftool` | image | exiftool (+ GPS finding séparé) |
| 19 | `stegseek` | image | stegseek (LSB crack) |
| 20 | `instaloader` | instagram_handle | instaloader |

## 📁 Fichiers

```
agent/osint/connectors/kali/
├── __init__.py            (auto-import des 20)
├── _helpers.py            (parse_urls/emails/domains)
├── sherlock.py
├── maigret.py
├── holehe.py
├── theharvester.py
├── sublist3r.py
├── subfinder.py
├── amass.py
├── whois_kali.py
├── dnsenum.py
├── dig_kali.py
├── host_kali.py
├── nmap_kali.py
├── shodan_cli.py
├── waybackurls.py
├── gau.py
├── photon.py
├── googler.py
├── exiftool.py
├── stegseek.py
└── instaloader.py
```

**Total** : ~1100 lignes de code (~50-80 par wrapper).

## 🧪 Tests (13 ajoutés)

`tests/test_osint_connectors_kali.py` :
- `test_all_20_connectors_registered` — auto-registration au import
- `test_each_connector_has_supports` — chaque c.supports non vide
- `test_each_connector_backend_kali` — backend="kali"
- `test_sherlock_supports_username_types`
- `test_holehe_supports_email`
- `test_exiftool_supports_image`
- `test_nmap_supports_ip_and_domain`
- `test_googler_supports_many_types`
- `test_connector_returns_failure_when_no_backend` — graceful no-Kali
- `test_sherlock_parses_stdout_output` — parse `[+] Site: URL`
- `test_holehe_parses_only_used` — parse `[+] site.com`
- `test_exiftool_parses_gps_finding` — JSON → GPS Finding séparé
- `test_dig_runs_for_each_record_type` — 7 record types A/AAAA/MX/TXT/NS/SOA/CNAME

## 🎯 Architecture connectors

- Auto-registration : chaque module fait `get_registry().register(<Connector>())` au import
- Pattern uniforme : `is_available()` check via `kali_runner`, `query()` async retourne `ConnectorResult`
- Helpers communs : `fail()`, `ok()`, `parse_urls/emails/domains`
- Sortie privilégiée : JSON (`--json`) quand outil le supporte (sherlock, maigret, subfinder, amass, exiftool, googler, theHarvester)

## ▶️ Suivant : Session 3

- `spiderfoot_client.py` — REST API daemon (200+ modules d'un coup)
- `reconng_client.py` — workspaces (100+ modules)
- 15 wrappers Kali restants : `gitleaks, trufflehog, zsteg, steghide, fierce, ffuf, gobuster, dirsearch, twint, osintgram, phoneinfoga, nuclei, linkedin2username, dnsrecon, recon-ng-cli`

## Liens
- [[phase7.6-session1-complete]]
- [[phase7.6-livraison-6-sessions]]
- [[phase7.6-connectors-kali]]
- [[phase7.6-kali-runner]]
