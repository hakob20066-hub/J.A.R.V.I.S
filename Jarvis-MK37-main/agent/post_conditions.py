"""
Post-conditions codables par tool.
Chaque checker prend (params, result) et retourne (ok: bool, reason: str).

Si pas de checker pour un tool → le Verifier fallback sur LLM-judge.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable


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


# ---------- checkers ----------

def _check_close_app(params: dict, result: str) -> tuple[bool, str]:
    from actions.close_app import _resolve_processes
    name = params.get("app_name", "")
    procs = _resolve_processes(name)
    if not procs:
        return False, f"unknown app '{name}'"
    time.sleep(0.5)
    alive = _is_running(procs)
    if alive:
        return False, f"process still alive: {', '.join(alive)}"
    return True, "process terminated"


def _check_open_app(params: dict, result: str) -> tuple[bool, str]:
    # Best-effort : au moins UNE fenêtre doit contenir le nom
    try:
        import pygetwindow as gw
    except Exception:
        return True, "pygetwindow unavailable (trust result)"
    name = (params.get("app_name", "") or "").lower()
    if not name:
        return True, "no name given"
    time.sleep(1.0)  # laisser le temps d'ouvrir
    for w in gw.getAllWindows():
        try:
            t = (w.title or "").lower()
            if name.split()[0] in t:
                return True, f"window found: {w.title[:60]}"
        except Exception:
            continue
    return False, f"no window matching '{name}'"


def _check_file_controller(params: dict, result: str) -> tuple[bool, str]:
    action = (params.get("action") or "").lower()
    path   = params.get("path", "")
    nm     = params.get("name", "")
    if action in ("write", "create_file"):
        target = _resolve_path(path, nm)
        if target and target.exists() and target.stat().st_size > 0:
            return True, f"file exists ({target.stat().st_size} bytes)"
        return False, f"file missing or empty: {target}"
    if action == "delete":
        target = _resolve_path(path, nm)
        if target and not target.exists():
            return True, "deleted"
        return False, f"still exists: {target}"
    return True, "action not checked"


def _resolve_path(path: str, name: str) -> Path | None:
    try:
        if (path or "").lower() == "desktop":
            base = Path.home() / "Desktop"
        else:
            base = Path(path) if path else Path.home()
        if name:
            return base / name
        return base
    except Exception:
        return None


def _check_reminder(params: dict, result: str) -> tuple[bool, str]:
    if "set" in (result or "").lower() or "reminder" in (result or "").lower():
        return True, "reminder acknowledged"
    return False, "no confirmation in result"


POST_CONDITIONS: dict[str, Callable[[dict, str], tuple[bool, str]]] = {
    "close_app":       _check_close_app,
    "open_app":        _check_open_app,
    "file_controller": _check_file_controller,
    "reminder":        _check_reminder,
}


def check(tool: str, params: dict, result: str) -> tuple[bool | None, str]:
    """
    True  = post-condition satisfied
    False = failed (hard evidence)
    None  = no checker → let LLM decide
    """
    fn = POST_CONDITIONS.get(tool)
    if not fn:
        return None, "no-checker"
    try:
        ok, reason = fn(params or {}, result or "")
        return ok, reason
    except Exception as e:
        return None, f"checker error: {e}"
