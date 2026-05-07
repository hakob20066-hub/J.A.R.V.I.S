---
title: Phase 7.6 — KaliRunner (détection backend)
date: 2026-05-05
tags: [phase7.6, kali, wsl]
linked_code: agent/osint/kali_runner.py
parent_moc: [[00-MOC/MOC-Phases]]
---

Détecte au boot le meilleur backend Kali :
1. WSL Kali (`wsl -d kali-linux -- which sherlock`) — **prioritaire**
2. WSL Ubuntu + apt-installed tools
3. Native Linux
4. Docker `kalilinux/kali-rolling`
5. Aucun → fallback Python

**Si WSL absent au boot** : popup user 'Installer WSL+Kali ?' (lock décision Phase 7.6).

API : `is_tool_available(name)`, `run(cmd, timeout, json_output)`, `install_tool(pkg)`.

## Liens
- [[phase7.6-spiderfoot-client]]
- [[phase7.6-wizard-step-4.6]]
- [[01-Concepts/concept-kali-wsl]]
