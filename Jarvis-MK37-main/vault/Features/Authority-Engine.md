---
title: Authority Engine — gating + audit
date: 2026-04-29
tags: [feature, security, authority, mk37]
priority: high
---

# Authority Engine

> Gating des actions sensibles + audit JSONL.
> Fichier : `agent/authority.py`
> Config : `config/authority.json`
> Audit : `memory/authority_audit.log`

---

## Décision

`check(tool, parameters)` retourne :

| Verdict | Sens |
|---------|------|
| `("allow", reason)` | Exécuter librement |
| `("ask", reason)` | Demander confirmation (callback UI/voice) |
| `("deny", reason)` | Bloquer |

---

## Modes

```json
{ "mode": "balanced" }   // paranoid | balanced | autonomous
```

| Mode | Comportement |
|------|-------------|
| **paranoid** | Tout `ask` sauf allowlist explicite |
| **balanced** | Allowlist auto, `ask_for` demande, reste allow |
| **autonomous** | Tout allow sauf denylist |

---

## Defaults (`config/authority.json`)

**Allowlist** (auto-approve) : `web_search`, `weather_report`, `youtube_video`, `screen_process`, `flight_finder`, `reminder`

**Ask for** : `shutdown_jarvis`, `file_controller:delete`, `file_controller:move`, `computer_settings`, `computer_control:hotkey`, `desktop_control:clean`, `game_updater:install`, `send_message`, `generated_code`

---

## Audit trail

`memory/authority_audit.log` (JSONL, append-only) :

```json
{"ts": 1714382400.12, "tool": "file_controller", "params": {...}, "verdict": "ask", "reason": "ask_for matched", "user_decision": "approved"}
```

---

## Pattern matching

Format `tool:sub_action` reconnu — `file_controller:delete` ne matche que les deletes, pas `read`/`list`. Granularité fine.

---

## Liens

- [[Architecture/Overview]]
- [[Operations/Setup-Env]]
- [[Docs/Actions-Tools]]
