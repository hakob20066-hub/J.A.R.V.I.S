---
title: Concept — Maltego .mtgx (XML graphe)
date: 2026-05-05
tags: [concept, maltego, mtgx, graph]
parent_moc: [[00-MOC/MOC-Concepts]]
---

Format XML natif Maltego (`.mtgx`). Importable direct dans Maltego CE/Pro pour analyse graphique avancée.

Structure : `<MaltegoMessage>` → `<Entities>` (nodes typés Maltego) + `<Links>` (edges avec weight et label).

Jarvis génère .mtgx + lance `maltego <file>.mtgx` (lock décision auto-open) → Maltego s'ouvre avec graphe pré-chargé.

## Liens
- [[14-Phases/phase7.6-maltego-export]]
