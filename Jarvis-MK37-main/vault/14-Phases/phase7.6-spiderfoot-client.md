---
title: Phase 7.6 — SpiderFoot client (200 modules d'un coup)
date: 2026-05-05
tags: [phase7.6, spiderfoot, kali]
parent_moc: [[00-MOC/MOC-Phases]]
---

SpiderFoot lancé en daemon (`spiderfoot -l 127.0.0.1:5001`) **à la demande au 1er OSINT** — PAS auto au boot Jarvis, économise ~500MB RAM si OSINT pas utilisé.

Wrapper REST API : `POST /startscan`, poll `/scanstatus/{id}`, `GET /scaneventresults/{id}`.

**1 client = 200 sources OSINT**.

## Liens
- [[phase7.6-kali-runner]]
- [[phase7.6-reconng-client]]
- [[01-Concepts/concept-spiderfoot]]
