---
title: Phase 7.6 — Wizard step 4.6 (OBLIGATOIRE)
date: 2026-05-05
tags: [phase7.6, wizard, setup]
parent_moc: [[00-MOC/MOC-Phases]]
---

**Step obligatoire au 1er boot** (lock décision user). Affiche :
1. Détection backend Kali (WSL/native/docker/none)
2. Si none → propose installer WSL+Kali (prompt user, pas silencieux)
3. Liste outils détectés vs manquants → bouton 'Install missing (apt)'
4. Form `self_identities` (name, emails, handles, phones, addresses) — tous optionnels
5. Disclaimer légal RGPD/CCPA obligatoire à signer

Sans step 4.6 complétée → `osint_lookup` désactivé au runtime.

## Liens
- [[phase7.6-kali-runner]]
- [[phase7.6-safety-legal-guard]]
