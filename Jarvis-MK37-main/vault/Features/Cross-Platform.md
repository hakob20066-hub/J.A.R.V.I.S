---
title: Cross-Platform — Windows / macOS / Linux
date: 2026-04-29
tags: [feature, cross-platform, mk37]
---

# Cross-Platform Support

> MK37 tourne sur **Windows, macOS et Linux**. Statut : *expérimental* (en validation continue).

---

## Statut par OS

| OS | Statut | Notes |
|----|--------|-------|
| **Windows 10/11** | ✅ Stable | Plateforme historique, tous les tools testés |
| **macOS** | ⚠️ Expérimental | Core OK, certains tools OS-specific peuvent varier |
| **Linux** | ⚠️ Expérimental | Core OK, validation en cours sur Ubuntu/Fedora |

---

## Stratégie d'implémentation

### Path resolution
Plus de chemins hardcodés Windows. Tout passe par `Path(...).resolve()`.

### Subprocess / shell
- Windows : `cmd.exe`, `powershell`
- macOS : `bash`, `zsh`, AppleScript via `osascript`
- Linux : `bash`, `xdotool` pour GUI control

### GUI control
- Windows : `pywinauto` + `pygetwindow` + `pyautogui`
- macOS : `pyautogui` + AppleScript
- Linux : `pyautogui` + `xdotool`/`wmctrl`

### Audio
`sounddevice` est déjà cross-platform (PortAudio).

---

## Note d'installation

> ⚠️ Certaines libs OS-specific (ex: `comtypes`, `pycaw`, `win10toast` sur Windows) ne sont pas bundled dans `requirements.txt` pour garder l'install légère.
> Si `ModuleNotFoundError` → `pip install <module>` selon ton OS.

Voir [[Operations/Setup-Env]].

---

## Liens

- [[Docs/Project-Overview]]
- [[Operations/Setup-Env]]
- [[Architecture/Stack-Technique]]


## Liens Transverses
- [[08-Tools/tool-delegate_task-overview.md]]
- [[08-Tools/tool-computer_control-params.md]]
