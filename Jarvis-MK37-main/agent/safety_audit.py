"""
Phase 7.5 — Safety Audit & Demo Mode

1. Audit log persistant : tout évènement potentiellement risqué (action LAM,
   command shell, file write, mission scheduled, kill-switch trigger, etc.)
   est append en JSONL dans memory/safety_audit.log. Sert de trace forensique.

2. Demo mode : flag global dans config/runtime.json. Quand True, les modules
   "actifs" (futur LAM phase 9, certains specialists, dev_agent) doivent
   refuser d'exécuter et logger l'intent au lieu d'agir.

3. Action history : stack en mémoire des dernières actions exécutées avec
   leur "undo callback" si rollbackable. Sert au bouton rollback de l'UI.
"""
from __future__ import annotations

import json
import sys
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR     = _base_dir()
AUDIT_PATH   = BASE_DIR / "memory" / "safety_audit.log"
RUNTIME_PATH = BASE_DIR / "config" / "runtime.json"

_AUDIT_LOCK   = threading.Lock()
_HISTORY_LOCK = threading.Lock()
# Stack des actions récentes (max 50). Chaque entrée = dict avec undo callable.
_ACTION_HISTORY: deque = deque(maxlen=50)


# ───────────────────────── Audit log ─────────────────────────

def audit_log(event_type: str, details: Optional[dict[str, Any]] = None) -> None:
    """
    Append un évènement au log d'audit. Best-effort : ne lève jamais.

    event_type : court identifiant (ex: "mission_start", "kill_switch",
                 "demo_toggle", "rollback", "lam_action", "shell_exec")
    details    : payload arbitraire (sera sérialisé en JSON)
    """
    try:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts":    datetime.now().isoformat(timespec="seconds"),
            "event": event_type,
            "details": details or {},
        }
        line = json.dumps(record, ensure_ascii=False)
        with _AUDIT_LOCK:
            with open(AUDIT_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception as e:
        print(f"[SafetyAudit] ⚠️ failed to log event '{event_type}': {e}")


def read_recent_audit(limit: int = 50) -> list[dict]:
    """Renvoie les N derniers events (ordre chronologique inverse)."""
    if not AUDIT_PATH.exists():
        return []
    try:
        with _AUDIT_LOCK:
            with open(AUDIT_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
        out = []
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        out.reverse()
        return out
    except Exception:
        return []


# ───────────────────────── Demo mode ─────────────────────────

def _load_runtime() -> dict:
    if not RUNTIME_PATH.exists():
        return {}
    try:
        return json.loads(RUNTIME_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_runtime(data: dict) -> None:
    RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def is_demo_mode() -> bool:
    """True si demo_mode actif (toutes les actions risquées doivent loguer
    leur intent au lieu d'exécuter)."""
    return bool(_load_runtime().get("demo_mode", False))


def set_demo_mode(enabled: bool, reason: str = "") -> None:
    rt = _load_runtime()
    previous = bool(rt.get("demo_mode", False))
    rt["demo_mode"] = bool(enabled)
    _save_runtime(rt)
    audit_log("demo_toggle", {"from": previous, "to": bool(enabled), "reason": reason})


# ───────────────────────── Action history & rollback ─────────────────────────

def push_action(
    name: str,
    summary: str,
    undo: Optional[Callable[[], str]] = None,
    metadata: Optional[dict] = None,
) -> None:
    """
    Enregistre une action exécutée + son undo (si rollbackable).

    name     : court id ex "file_write", "mission_run", "shell"
    summary  : description user-friendly
    undo     : callable qui annule l'action et retourne un string de résultat,
               OU None si l'action est irréversible (ex: msg envoyé)
    """
    entry = {
        "ts":      datetime.now().isoformat(timespec="seconds"),
        "name":    name,
        "summary": summary[:200],
        "metadata": metadata or {},
        "undo":    undo,           # callable (pas sérialisé, vit en RAM)
        "rollbackable": undo is not None,
    }
    with _HISTORY_LOCK:
        _ACTION_HISTORY.append(entry)
    audit_log("action_executed", {
        "name": name, "summary": summary[:200],
        "rollbackable": undo is not None,
    })


def get_history(limit: int = 20) -> list[dict]:
    """Liste des actions récentes (sans le callable undo, pour exposer à l'UI)."""
    with _HISTORY_LOCK:
        items = list(_ACTION_HISTORY)[-limit:]
    return [
        {k: v for k, v in entry.items() if k != "undo"}
        for entry in reversed(items)
    ]


def rollback_last() -> dict:
    """
    Tente d'annuler la dernière action rollbackable.
    Retourne {"ok": bool, "name": str, "result": str, "reason": str}.
    """
    with _HISTORY_LOCK:
        # Cherche la plus récente avec un undo
        target_idx = None
        for i in range(len(_ACTION_HISTORY) - 1, -1, -1):
            if _ACTION_HISTORY[i].get("undo"):
                target_idx = i
                break
        if target_idx is None:
            audit_log("rollback_attempt", {"ok": False, "reason": "no rollbackable action"})
            return {"ok": False, "reason": "Aucune action rollbackable récente."}
        entry = _ACTION_HISTORY[target_idx]
        undo  = entry["undo"]

    try:
        result = undo() or "rolled back"
        # Marque l'entrée comme rollback effectué (mais on la garde dans l'historique)
        with _HISTORY_LOCK:
            _ACTION_HISTORY[target_idx]["undo"] = None
            _ACTION_HISTORY[target_idx]["rolled_back"] = True
        audit_log("rollback_attempt", {
            "ok": True, "name": entry["name"], "result": str(result)[:200],
        })
        return {"ok": True, "name": entry["name"], "result": str(result)[:200]}
    except Exception as e:
        audit_log("rollback_attempt", {
            "ok": False, "name": entry["name"], "error": str(e)[:200],
        })
        return {"ok": False, "name": entry["name"], "reason": f"rollback failed: {e}"}


def clear_history() -> None:
    with _HISTORY_LOCK:
        _ACTION_HISTORY.clear()


# ───────────────────────── Kill switch ─────────────────────────

_KILL_CALLBACKS: list[Callable[[], None]] = []
_KILL_LOCK = threading.Lock()


def register_kill_callback(cb: Callable[[], None]) -> None:
    """Permet à un module (mission_runner, lam_controller, etc.) de s'inscrire
    pour être stoppé d'urgence quand `trigger_kill_switch()` est appelé."""
    with _KILL_LOCK:
        _KILL_CALLBACKS.append(cb)


def trigger_kill_switch(reason: str = "user_hotkey") -> dict:
    """
    Stoppe d'urgence tous les modules enregistrés + force demo_mode = True
    pour bloquer toute nouvelle action. Idempotent.
    """
    audit_log("kill_switch", {"reason": reason})
    set_demo_mode(True, reason=f"kill_switch:{reason}")
    failed = []
    with _KILL_LOCK:
        cbs = list(_KILL_CALLBACKS)
    for cb in cbs:
        try:
            cb()
        except Exception as e:
            failed.append(str(e))
    return {"ok": len(failed) == 0, "stopped": len(cbs), "errors": failed}
