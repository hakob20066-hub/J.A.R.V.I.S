---
title: Phase 7.6 — Audit log signé HMAC
date: 2026-05-05
tags: [phase7.6, audit, hmac, security]
parent_moc: [[00-MOC/MOC-Phases]]
---

`memory/osint_audit.log` JSONL append-only, **chaque entry signée HMAC-SHA256** :
```jsonl
{"ts":..., "target_hash":"sha256:...", "mode":"external_target", "depth":3, "sources":[...], "consent":"popup_v1_2026-05-05", "hmac":"..."}
```

Hashing target sensible (jamais en clair). Rotation par taille (10MB).

## Liens
- [[phase7.6-safety-legal-guard]]
