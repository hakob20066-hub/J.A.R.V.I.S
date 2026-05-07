---
title: Phase 7.6 — AdaptiveScheduler (pool dynamique)
date: 2026-05-05
tags: [phase7.6, scheduler, perf]
parent_moc: [[00-MOC/MOC-Phases]]
---

Pool de workers asyncio dont taille s'ajuste en continu :
- min=2, max_cap=20
- réduit si CPU>80% ou RAM dispo<1GB pendant 5s
- augmente si CPU<50% et queue>pool_size

Évite à la fois la lenteur (parallélisation maxi) et le freeze système.

## Liens
- [[phase7.6-pivot-cascade]]
