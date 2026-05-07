---
title: Phase 7.6 — Persistance reports (tout gardé, indexé)
date: 2026-05-05
tags: [phase7.6, persistance, reports, sqlite]
parent_moc: [[00-MOC/MOC-Phases]]
---

**Tous rapports conservés** indéfiniment (lock décision) dans `memory/osint_reports/<target_hash>__<iso_ts>/` :
- report.json + report.html (viewer) + report.mtgx + report.csv + report.md
- findings.jsonl + images/ EXIF stripped

**Index SQLite** `_index.db` searchable par target_hash, type, mode, date, sources.
Onglet '📂 Past Reports' dans le panel pour navigation/recherche.

## Liens
- [[phase7.6-osint-overview]]
