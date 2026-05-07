---
title: Phase 7.6 — Export Maltego natif (.mtgx + .csv)
date: 2026-05-05
tags: [phase7.6, maltego, export]
parent_moc: [[00-MOC/MOC-Phases]]
---

`MaltegoExporter` génère `.mtgx` (XML graphe importable Maltego CE/Pro) et `.csv` fallback.

**Mapping entités** : Person, EmailAddress, Phone, Domain, IPv4Address, Alias, affiliation.{Twitter,Instagram,LinkedIn}, Location (lat/lon), Image, Hash, BitcoinAddress.

**Auto-open** (lock décision) : Jarvis lance `maltego <path>.mtgx` après export → fenêtre Maltego s'ouvre avec graphe pré-chargé.

## Liens
- [[phase7.6-ui-report-window]]
- [[01-Concepts/concept-maltego-mtgx]]
