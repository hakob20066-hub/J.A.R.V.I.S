---
title: Phase 7.6 — UI panel OSINT (gauche, on-demand)
date: 2026-05-05
tags: [phase7.6, ui, panel]
parent_moc: [[00-MOC/MOC-Phases]]
---

Panneau latéral **gauche** dans `ui.html`, **collapsé par défaut**, s'ouvre **uniquement** quand tool `osint_lookup` est appelé (lock décision).

**Contenu** : target + mode badge, progress bar live, findings streamés (slide-in), boutons 'Open Full Report' + 'Cancel'.

**Drag-drop image** activé sur le panel (priorité 1).

Bridge Python ↔ JS : `_OSINTApi` class dans `ui.py`.

## Liens
- [[phase7.6-ui-report-window]]
- [[phase7.6-drag-drop-image]]
