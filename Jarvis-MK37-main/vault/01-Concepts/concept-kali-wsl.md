---
title: Concept — Kali Linux via WSL
date: 2026-05-05
tags: [concept, kali, wsl, windows]
parent_moc: [[00-MOC/MOC-Concepts]]
---

Windows Subsystem for Linux (WSL2) permet de faire tourner Kali natif sur Windows. Détection : `wsl -d kali-linux -- which <tool>`.

**Avantages** : 600+ outils Kali, apt update, pas de re-implémentation Python.
**Latence** : cold-start ~500ms par commande → atténuée par pool subprocess persistants.
**Coût RAM** : WSL2 ~1-2GB en idle.

## Liens
- [[14-Phases/phase7.6-kali-runner]]
- [[concept-spiderfoot]]
