---
title: Phase 7.6 — Drag-drop image dans panel (P1)
date: 2026-05-05
tags: [phase7.6, ui, drag-drop, image]
parent_moc: [[00-MOC/MOC-Phases]]
---

Drop image sur le panel OSINT → Jarvis lance auto-OSINT type=image (cascade reverse search + EXIF + stéganalyse + face recognition si keys présentes).

Pipeline JS → `osint_save_dropped_image(filename, b64)` → `osint_lookup_image(path)` → engine déclenche cascade type=image.

## Liens
- [[phase7.6-ui-panel-gauche]]
