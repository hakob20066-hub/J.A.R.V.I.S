---
title: Catalogue Actions & Tools — MK37
date: 2026-04-29
tags: [docs, tools, actions]
---

# Catalogue des Actions — 21 outils

> Toutes les actions sont dans `actions/`. Chacune expose une fonction principale appelée par le tool dispatcher Gemini Live.
> Liens : [[Docs/Project-Overview]] | [[Features/Authority-Engine]] | [[Features/Specialists-9-Roles]]

---

## Système & desktop

| Tool | Fichier | Description |
|------|---------|-------------|
| **open_app** | `actions/open_app.py` | Lance une application par nom |
| **close_app** | `actions/close_app.py` | Ferme une application *(NEW MK37)* |
| **computer_control** | `actions/computer_control.py` | Shutdown, restart, sleep, hibernate |
| **computer_settings** | `actions/computer_settings.py` | Volume, luminosité, paramètres |
| **desktop** | `actions/desktop.py` | Bureau, fond d'écran |
| **file_controller** | `actions/file_controller.py` | CRUD fichiers |
| **screen_processor** | `actions/screen_processor.py` | Capture & analyse écran |

## Web & recherche

| Tool | Fichier | Description |
|------|---------|-------------|
| **web_search** | `actions/web_search.py` | Gemini google_search + DDG fallback |
| **browser_control** | `actions/browser_control.py` | Playwright |
| **flight_finder** | `actions/flight_finder.py` | Google Flights |
| **weather_report** | `actions/weather_report.py` | Météo via API |
| **youtube_video** | `actions/youtube_video.py` | Contrôle YouTube |

## Communication

| Tool | Fichier | Description |
|------|---------|-------------|
| **send_message** | `actions/send_message.py` | WhatsApp, Telegram |
| **reminder** | `actions/reminder.py` | Programmation rappels |

## Code & dev

| Tool | Fichier | Description |
|------|---------|-------------|
| **code_helper** | `actions/code_helper.py` | Aide code IA (un fichier) |
| **dev_agent** | `actions/dev_agent.py` | Agent dev multi-fichiers |

## Gaming

| Tool | Fichier | Description |
|------|---------|-------------|
| **game_updater** | `actions/game_updater.py` | Steam / Epic install + update |

## OSINT *(NEW MK37)*

| Tool | Fichier | Description |
|------|---------|-------------|
| **people_search** | `actions/people_search.py` | Pipeline OSINT nom+prénom → profils + emails + leaks |
| **online_presence_audit** | `actions/online_presence_audit.py` | Audit Instagram → comptes liés |

Voir [[Features/OSINT-Tools]].

## Agent / workflow *(NEW MK37)*

| Tool | Fichier | Description |
|------|---------|-------------|
| **delegate_task** | `actions/delegate_task.py` | Dispatche à un [[Features/Specialists-9-Roles\|spécialiste]] |
| **morning_briefing** | `actions/morning_briefing.py` | Briefing matinal |

---

## Authority gating

Chaque tool call passe par [[Features/Authority-Engine]]. Selon `mode` (`paranoid` / `balanced` / `autonomous`) et la liste `ask_for`, certains tools demandent confirmation explicite avant exécution.

`config/authority.json` actuel :
- **allowlist** : web_search, weather_report, youtube_video, screen_process, flight_finder, reminder
- **ask_for** : shutdown_jarvis, file_controller:delete, file_controller:move, computer_settings, computer_control:hotkey, desktop_control:clean, game_updater:install, send_message, generated_code

---

## Liens

- [[Features/Authority-Engine]]
- [[Features/Specialists-9-Roles]]
- [[Architecture/Agent-Dispatcher]]
