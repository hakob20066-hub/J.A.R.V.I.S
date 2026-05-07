---
title: Phase 7.6 — Session 3 ✅ DONE (SpiderFoot + recon-ng + 15 wrappers)
date: 2026-05-07
tags: [phase7.6, osint, session3, livraison, done, kali, spiderfoot, reconng]
parent_moc: [[00-MOC/MOC-Phases]]
---

# Session 3 — SpiderFoot + recon-ng + 15 wrappers Kali

**Statut** : ✅ DONE
**Tests** : **210/210 PASS** (190 base + 20 Session 3)
**Total connecteurs registrés** : **36** (20 Session 2 + 15 Session 3 + spiderfoot + recon-ng)

## 📦 Livré Session 3

### 2 Méta-clients (~350 lignes)

| Module | Lignes | Modules effectifs |
|---|---|---|
| `agent/osint/spiderfoot_client.py` | ~200 | **200+ modules SpiderFoot** via REST API daemon |
| `agent/osint/reconng_client.py` | ~150 | **100+ modules recon-ng** via workspace + script.rc |

**SpiderFoot** : daemon lancé à la demande au 1er OSINT (lock décision). REST API `127.0.0.1:5001`. `_ensure_running()` vérifie + lance via `kali_runner` en nohup background. Poll status, fetch events, mappe en `Finding`.

**recon-ng** : génère script.rc dynamique avec modules + options + run, exécute dans workspace dédié `jarvis_<target_hash>`. Parse stdout pour extraire rows `[*] [type] key => value`.

### 15 wrappers Kali Session 3 (~50 lignes/each, ~750 total)

| # | Wrapper | Cibles | Outil Kali |
|---|---|---|---|
| 1 | `gitleaks` | domain (github URL) | gitleaks (clone+scan secrets) |
| 2 | `trufflehog` | domain (github URL) | trufflehog git |
| 3 | `zsteg` | image PNG/BMP | zsteg LSB |
| 4 | `steghide` | image JPG | steghide info |
| 5 | `fierce` | domain | fierce DNS recon |
| 6 | `ffuf` | domain | ffuf web fuzz |
| 7 | `gobuster` | domain | gobuster dir |
| 8 | `dirsearch` | domain | dirsearch |
| 9 | `twint` | social_handle, username, pseudonym | twint Twitter |
| 10 | `osintgram` | instagram_handle | osintgram (info, emails, captions) |
| 11 | `phoneinfoga` | phone | phoneinfoga scan |
| 12 | `nuclei` | domain, ip | nuclei templates JSONL |
| 13 | `linkedin2username` | person_full | + fallback variations Python |
| 14 | `dnsrecon` | domain | dnsrecon JSON |
| 15 | `recon_ng_cli` | domain, email, person | alias ReconNgConnector |

### 📁 Structure ajoutée

```
agent/osint/
├── spiderfoot_client.py     🆕  (REST API + Connector)
├── reconng_client.py        🆕  (CLI + Connector)
└── connectors/kali/
    ├── gitleaks.py           🆕
    ├── trufflehog.py         🆕
    ├── zsteg.py              🆕
    ├── steghide.py           🆕
    ├── fierce.py             🆕
    ├── ffuf.py               🆕
    ├── gobuster.py           🆕
    ├── dirsearch.py          🆕
    ├── twint.py              🆕
    ├── osintgram.py          🆕
    ├── phoneinfoga.py        🆕
    ├── nuclei.py             🆕
    ├── linkedin2username.py  🆕
    ├── dnsrecon.py           🆕
    └── recon_ng_cli.py       🆕  (alias re-export ReconNgConnector)
```

## 🧪 Tests (20 ajoutés dans `test_osint_session3.py`)

- **Registration** (3) : tous présents, count ≥ 36, supports valides
- **Type sanity** (5) : phoneinfoga=phone, zsteg/steghide=image, ffuf/gobuster/dirsearch=domain, linkedin2username=person, spiderfoot=multi
- **Parsing** (7) : phoneinfoga, nuclei JSONL, twint JSON, linkedin2username variations, gitleaks github-required, zsteg skip JPG, steghide skip PNG
- **SpiderFoot client** (2) : daemon dead → empty, no Kali → unavailable
- **Recon-ng client** (3) : build_rc format, parse_stdout rows, no Kali → unavailable

## 🎯 Patterns notables

- **Auto-degradation** : chaque connecteur skip silencieusement si tool absent (`is_available() == False`) → engine continue
- **Type-restrictif** : zsteg PNG/BMP, steghide JPG, gitleaks github-only → fail-fast avec error parlant
- **Fallback Python** : `linkedin2username` génère variations classiques en Python si CLI échoue
- **Méta = `recon-ng` + `recon_ng_cli`** : 2 noms vers 1 client (rétrocompat)

## ▶️ Prochaine session : Session 4

- 25 connecteurs Python fallback (`agent/osint/connectors/python/`)
- 4 analyzers cross-cutting (`behavior`, `network`, `historical`, `metadata`)
- Update engine pour appeler analyzers post-cascade
- ~30 tests supplémentaires

## Liens
- [[phase7.6-session2-complete]]
- [[phase7.6-livraison-6-sessions]]
- [[phase7.6-spiderfoot-client]]
- [[phase7.6-reconng-client]]
- [[phase7.6-connectors-kali]]
