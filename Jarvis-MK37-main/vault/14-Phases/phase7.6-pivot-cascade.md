---
title: Phase 7.6 — Auto-pivot cascade (depth 2 default, max 3)
date: 2026-05-05
tags: [phase7.6, pivot, cascade]
parent_moc: [[00-MOC/MOC-Phases]]
---

Chaque finding pivotable → nouvelle Target ajoutée à la queue active. Streaming continu, pas de phases discrètes.

**Exemple** : `@fatihmakes` → Sherlock trouve GitHub → email du profil GitHub → HIBP leaks → ...

**Garde-fous** : `max_total_targets=500`, `max_runtime=600s`, `max_depth=3`, kill switch Phase 7.5 (`Ctrl+Alt+Esc`).

## Liens
- [[phase7.6-scheduler-adaptive]]
- [[phase7.6-targets-12]]
- [[01-Concepts/concept-osint-pivot]]
