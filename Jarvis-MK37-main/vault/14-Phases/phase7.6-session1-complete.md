---
title: Phase 7.6 — Session 1 ✅ DONE (engine core + UI)
date: 2026-05-07
tags: [phase7.6, osint, session1, livraison, done]
parent_moc: [[00-MOC/MOC-Phases]]
---

# Session 1 — Engine OSINT core + UI panel

**Statut** : ✅ DONE
**Date** : 2026-05-07
**Tests** : 47/47 OSINT + 130 base = **177/177 PASS**

## 📦 Livrables

### Code (`agent/osint/` — 12 modules, ~1335 lignes)

| Module | Lignes | Rôle |
|---|---|---|
| `__init__.py` | 20 | Public API |
| `target.py` | 130 | TargetNormalizer (12 types auto-détectés) |
| `audit.py` | 130 | JSONL HMAC-SHA256 + rotation 10MB |
| `safety.py` | 175 | LegalGuard self_audit vs external_target |
| `ratelimit.py` | 55 | TokenBucket par connecteur |
| `kali_runner.py` | 200 | Detect WSL Kali / Ubuntu / native / docker |
| `scheduler.py` | 110 | AdaptiveScheduler (psutil CPU/RAM) |
| `pivot.py` | 80 | PivotEngine cascade |
| `ui_bridge.py` | 100 | Events → JarvisUI (start/progress/finding/...) |
| `engine.py` | 240 | OSINTEngine orchestrateur |
| `connectors/base.py` | 90 | Connector ABC + Registry |
| `connectors/__init__.py` | 5 | Package init |

### UI

- `ui.py` — `_OSINTApi` class + 7 méthodes `osint_panel_*` sur JarvisUI
- `ui.html` — panel gauche on-demand : header, target, progress bar gradient, connectors list, findings list (slide-in), drop overlay, ~150 lignes CSS + ~130 lignes JS

### Tests (47)

- `test_osint_target.py` — 19 tests (12 types × variantes)
- `test_osint_safety.py` — 6 tests (self/external/quota/refus default)
- `test_osint_audit.py` — 5 tests (HMAC sign/verify/tamper/tail/empty)
- `test_osint_pivot.py` — 6 tests (extraction/dedup/cap/explicit/url-domain)
- `test_osint_engine.py` — 6 tests (cascade/cancel/blocked/empty/unknown)
- `test_osint_kali_runner.py` — 5 tests (detect/wrap native+wsl/cache)

## 🎯 Comportements validés

- Auto-détection 12 types cible
- Cascade pivot depth 1→3 streaming
- Hard timeout `MAX_RUNTIME_SECONDS=600s`
- Cap `MAX_TOTAL_TARGETS=500`
- Cancel runtime via flag thread-safe (avec param `reset_cancel`)
- LegalGuard self vs external + quota dur 5/jour
- Refus par défaut face recognition (image+deep)
- Audit HMAC-SHA256 signé + rotation 10MB
- Panel gauche on-demand (transform translateX, transition 0.35s)
- Drag-drop image fonctionnel (base64 → save → engine.lookup)
- Détection 5 backends Kali (WSL Kali / WSL Ubuntu / native / docker / none)

## ▶️ Suivant : Session 2 (20 wrappers Kali)

- sherlock, maigret, holehe, theHarvester
- sublist3r, subfinder, amass
- whois, dig, dnsenum, host
- nmap, shodan-cli
- waybackurls, gau, photon, googler
- exiftool, stegseek, instaloader

## Liens
- [[phase7.6-livraison-6-sessions]]
- [[phase7.6-osint-overview]]
- [[phase7.6-targets-12]]
- [[phase7.6-pivot-cascade]]
- [[phase7.6-kali-runner]]
- [[phase7.6-safety-legal-guard]]
- [[phase7.6-audit-log-hmac]]
- [[phase7.6-ui-panel-gauche]]
- [[phase7.6-drag-drop-image]]
