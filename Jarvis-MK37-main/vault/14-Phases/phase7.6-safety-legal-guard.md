---
title: Phase 7.6 — LegalGuard (self_audit vs external_target)
date: 2026-05-05
tags: [phase7.6, safety, legal, rgpd]
parent_moc: [[00-MOC/MOC-Phases]]
---

**Mode `self_audit`** : handles déclarés au wizard step 4.6 → autoallow.
**Mode `external_target`** : disclaimer popup obligatoire au 1er usage (RGPD/CCPA), consentement loggé HMAC, rate limit dur **5 lookups MAX-mode/jour**.

Cibles `image` face recognition + `address` voisinage social = **refus par défaut** sauf override explicite. Authority `osint_lookup:external_target:maximum` permanent dans `ask_for`.

## Liens
- [[phase7.6-audit-log-hmac]]
- [[phase7.6-wizard-step-4.6]]
