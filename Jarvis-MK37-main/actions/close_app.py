"""
close_app — ferme une application avec vérification.

Stratégie escalade :
  1. Graceful close via pygetwindow (fenêtre cible + WM_CLOSE)
  2. taskkill /F /IM <proc> (force)
  3. Vérif psutil : process encore vivant ? → échec explicite, pas de "c'est bon" menteur.

Exemples de noms :
  "vs code", "vscode", "code" → Code.exe
  "chrome"                    → chrome.exe
"""

from __future__ import annotations

import subprocess
import time
from typing import Optional


# Alias nom utilisateur → process Windows
ALIASES: dict[str, list[str]] = {
    "vs code":        ["Code.exe", "Code - Insiders.exe"],
    "vscode":         ["Code.exe", "Code - Insiders.exe"],
    "code":           ["Code.exe"],
    "chrome":         ["chrome.exe"],
    "firefox":        ["firefox.exe"],
    "brave":          ["brave.exe"],
    "edge":           ["msedge.exe"],
    "opera gx":       ["opera.exe", "opera_gx.exe"],
    "opera":          ["opera.exe"],
    "spotify":        ["Spotify.exe"],
    "discord":        ["Discord.exe"],
    "whatsapp":       ["WhatsApp.exe"],
    "steam":          ["steam.exe", "steamwebhelper.exe"],
    "notepad":        ["notepad.exe", "Notepad.exe"],
    "explorer":       ["explorer.exe"],
    "file explorer":  ["explorer.exe"],
    "cmd":            ["cmd.exe"],
    "powershell":     ["powershell.exe", "pwsh.exe"],
    "terminal":       ["WindowsTerminal.exe", "powershell.exe", "cmd.exe"],
}


def _resolve_processes(name: str) -> list[str]:
    n = (name or "").strip().lower()
    if not n:
        return []
    if n in ALIASES:
        return ALIASES[n]
    # fallback : nom direct + .exe
    if not n.endswith(".exe"):
        return [f"{n}.exe"]
    return [n]


def _is_running(proc_names: list[str]) -> list[str]:
    try:
        import psutil
    except Exception:
        return []
    alive = []
    lowers = {p.lower() for p in proc_names}
    for p in psutil.process_iter(["name"]):
        try:
            nm = (p.info.get("name") or "").lower()
            if nm in lowers:
                alive.append(nm)
        except Exception:
            continue
    return alive


def _graceful_close(proc_names: list[str]) -> None:
    try:
        import pygetwindow as gw
    except Exception:
        return
    lowers = [p.lower().replace(".exe", "") for p in proc_names]
    for w in gw.getAllWindows():
        try:
            title = (w.title or "").lower()
            if any(k in title for k in lowers):
                w.close()
        except Exception:
            continue


def _taskkill(proc_name: str) -> int:
    try:
        r = subprocess.run(
            ["taskkill", "/F", "/IM", proc_name],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode
    except Exception as e:
        print(f"[close_app] taskkill {proc_name} error: {e}")
        return -1


def close_app(parameters: dict, player=None, speak=None) -> str:
    name    = (parameters or {}).get("app_name", "")
    procs   = _resolve_processes(name)
    if not procs:
        return f"close_app: nothing resolved for '{name}'."

    alive_before = _is_running(procs)
    if not alive_before:
        return f"{name} was not running."

    # 1. Graceful
    _graceful_close(procs)
    time.sleep(1.0)
    alive = _is_running(procs)
    if not alive:
        return f"Closed {name}."

    # 2. Force via taskkill
    for p in procs:
        _taskkill(p)
    time.sleep(0.7)
    alive = _is_running(procs)
    if not alive:
        return f"Force-closed {name}."

    # Vérif finale
    still = ", ".join(alive)
    return f"close_app FAILED: {name} still running ({still})."
