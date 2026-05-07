---
title: Phase 7.6 — 12 types de cibles auto-détectés
date: 2026-05-05
tags: [phase7.6, target, normalizer]
parent_moc: [[00-MOC/MOC-Phases]]
---

`TargetNormalizer.detect(raw)` → type ∈ {email, domain, ip, username, instagram_handle, social_handle, person_full, address, phone, crypto, image, pseudonym}.

Chaque type déclenche un set spécifique de connecteurs via `SourceDispatcher.select(type)`. Cibles ambiguës (ex: 'fatih' = nom OU username) → demande clarification user.

## Liens
- [[phase7.6-pivot-cascade]]
- [[phase7.6-osint-overview]]
