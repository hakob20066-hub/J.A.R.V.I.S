---
title: Phase 7.6 — Fenêtre rapport (Cytoscape cyberpunk)
date: 2026-05-05
tags: [phase7.6, ui, report, cytoscape]
parent_moc: [[00-MOC/MOC-Phases]]
---

`osint_report.html` — pywebview window séparée, standalone (libs JS embarquées offline).

**Tabs** : Overview / Findings / Graph / Timeline / Behavior / Raw / Export.

**Graph Cytoscape.js** : layout cose-bilkent force-directed, glow cyberpunk, node shapes par type entité (round=person, hex=domain, diamond=leak), edge gradients, tooltips Tippy.js, right-click context menu (Pivot/Hide/Highlight cluster).

Plugins : cose-bilkent, popper+tippy, context-menus, edgehandles.

## Liens
- [[phase7.6-ui-panel-gauche]]
- [[phase7.6-maltego-export]]
