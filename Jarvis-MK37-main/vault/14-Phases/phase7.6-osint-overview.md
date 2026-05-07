---
title: Phase 7.6 — OSINT (Kali Hybrid) — Overview
date: 2026-05-05
tags: [phase7.6, osint, kali, architecture]
parent_moc: [[00-MOC/MOC-Phases]]
---

Phase intercalée entre 7.5 (Safety Net) et 8 (Perception). Moteur OSINT unifié multi-sources avec **Kali Linux en backend prioritaire** (WSL/native/docker), **fallback Python** si Kali absent.

**Capacités** : 12 types de cibles, 60+ wrappers Kali, 25 connecteurs Python fallback, 300+ sources via SpiderFoot+recon-ng, 4 analyseurs comportementaux, export Maltego .mtgx, UI dédiée (panel gauche on-demand + fenêtre rapport Cytoscape), persistance complète indexée.

## Liens
- [[phase7.6-objectif]]
- [[phase7.6-kali-runner]]
- [[phase7.6-targets-12]]
- [[phase7.6-livraison-6-sessions]]
