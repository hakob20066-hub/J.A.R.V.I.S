"""
Phase 7.5 — Hotkey global Ctrl+Alt+Esc → kill switch.

Backends (priorité décroissante) :
  1. keyboard (lib pip 'keyboard') — Windows root-free, le + simple
  2. pynput (multi-OS, root parfois requis sur Linux)
  3. fallback no-op (rien d'installé) — log warning et abandonne

Le listener tourne dans un thread daemon. Aucun blocking de la main loop.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from agent.safety_audit import audit_log, trigger_kill_switch


_LISTENER_SINGLETON: Optional["EmergencyStopListener"] = None


class EmergencyStopListener:
    def __init__(self, hotkey: str = "ctrl+alt+esc",
                 on_trigger: Optional[Callable[[], None]] = None):
        self.hotkey     = hotkey
        self.on_trigger = on_trigger or (lambda: trigger_kill_switch("hotkey"))
        self._backend   = self._pick_backend()
        self._stop      = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._emergency_active = False
        self._event_log: list[dict] = []
        self._log_lock  = threading.Lock()

    def _pick_backend(self) -> str:
        try:
            import keyboard  # noqa: F401
            return "keyboard"
        except Exception:
            pass
        try:
            from pynput import keyboard  # noqa: F401
            return "pynput"
        except Exception:
            pass
        print("[EmergencyStop] ⚠️ No hotkey backend (pip install keyboard) — kill switch disabled.")
        return "none"

    def start(self) -> None:
        if self._backend == "none":
            return
        if self._thread and self._thread.is_alive():
            return
        target = {
            "keyboard": self._loop_keyboard,
            "pynput":   self._loop_pynput,
        }.get(self._backend)
        if not target:
            return
        self._thread = threading.Thread(target=target, daemon=True, name="emergency-stop")
        self._thread.start()
        print(f"[EmergencyStop] 🟥 Kill switch armed ({self.hotkey}, backend={self._backend})")
        audit_log("kill_switch_armed", {"hotkey": self.hotkey, "backend": self._backend})

    def stop(self) -> None:
        self._stop.set()

    # ---------- backends ----------

    def _loop_keyboard(self) -> None:
        try:
            import keyboard
            keyboard.add_hotkey(self.hotkey, self._on_fire, suppress=False)
            self._stop.wait()
        except Exception as e:
            print(f"[EmergencyStop] ⚠️ keyboard backend error: {e}")

    def _loop_pynput(self) -> None:
        try:
            from pynput import keyboard as kb
            mapping = {
                # ctrl+alt+esc
                "ctrl+alt+esc": "<ctrl>+<alt>+<esc>",
            }
            combo = mapping.get(self.hotkey, self.hotkey)
            with kb.GlobalHotKeys({combo: self._on_fire}) as h:
                self._stop.wait()
                h.stop()
        except Exception as e:
            print(f"[EmergencyStop] ⚠️ pynput backend error: {e}")

    def _on_fire(self) -> None:
        print("[EmergencyStop] 🟥🟥🟥 KILL SWITCH TRIGGERED")
        self._emergency_trigger()

    def _emergency_trigger(self) -> None:
        self._emergency_active = True
        self._log_event("EMERGENCY_TRIGGER", "Kill switch fired")
        try:
            self.on_trigger()
        except Exception as e:
            print(f"[EmergencyStop] ⚠️ trigger callback error: {e}")

    def is_emergency_active(self) -> bool:
        return self._emergency_active

    def _log_event(self, event_type: str, details: str) -> None:
        entry = {"type": event_type, "details": details, "ts": time.time()}
        with self._log_lock:
            self._event_log.append(entry)
        print(f"[EmergencyStop] 📋 {event_type}: {details}")
        try:
            audit_log(event_type.lower(), {"details": details})
        except Exception:
            pass

    def get_status(self) -> dict:
        with self._log_lock:
            log_copy = list(self._event_log[-20:])
        return {
            "emergency_active": self._emergency_active,
            "backend": self._backend,
            "hotkey": self.hotkey,
            "recent_events": log_copy,
        }

    def shutdown(self) -> None:
        self.stop()
        print("[EmergencyStop] 🔕 Shutdown.")


def start_emergency_stop(**kw) -> EmergencyStopListener:
    """Singleton starter. Appelé une fois au boot par main.py."""
    global _LISTENER_SINGLETON
    if _LISTENER_SINGLETON is None:
        _LISTENER_SINGLETON = EmergencyStopListener(**kw)
    _LISTENER_SINGLETON.start()
    return _LISTENER_SINGLETON


def get_emergency_stop() -> EmergencyStopListener:
    """Retourne le singleton (le crée si besoin, sans le démarrer)."""
    global _LISTENER_SINGLETON
    if _LISTENER_SINGLETON is None:
        _LISTENER_SINGLETON = EmergencyStopListener()
    return _LISTENER_SINGLETON


def reset_emergency_stop() -> None:
    """Réinitialise le singleton (utile pour les tests)."""
    global _LISTENER_SINGLETON
    if _LISTENER_SINGLETON is not None:
        _LISTENER_SINGLETON.stop()
        _LISTENER_SINGLETON = None
