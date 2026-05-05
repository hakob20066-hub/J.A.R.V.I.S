"""
Emergency Stop System — Phase 7.5 Safety Net

Global hotkey Ctrl+Alt+Esc pour arrêter immédiatement toutes les actions LAM/automatisées.
Kill switch qui freeze les missions en cours et nettoie l'état.
"""

from __future__ import annotations

import threading
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False
    print("[EmergencyStop] ⚠️ keyboard module not available - hotkey disabled")

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
    pyautogui.FAILSAFE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    print("[EmergencyStop] ⚠️ pyautogui not available - mouse freeze disabled")


class EmergencyStop:
    """Gestionnaire d'arrêt d'urgence avec hotkey global et audit trail."""
    
    def __init__(self, audit_log_path: Optional[Path] = None):
        self._lock = threading.RLock()
        self._is_active = True
        self._emergency_triggered = False
        self._trigger_time: Optional[float] = None
        self._hotkey_registered = False
        self._callbacks: list[Callable[[], None]] = []
        
        # Audit log
        self.audit_log_path = audit_log_path or Path("memory/safety_audit.log")
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Enregistrer le hotkey si disponible
        if KEYBOARD_AVAILABLE:
            self._register_hotkey()
        
        self._log_event("SYSTEM_START", "Emergency stop system initialized")
    
    def _register_hotkey(self):
        """Enregistre le hotkey global Ctrl+Alt+Esc."""
        try:
            keyboard.add_hotkey('ctrl+alt+esc', self._emergency_trigger)
            self._hotkey_registered = True
            self._log_event("HOTKEY_REGISTERED", "Ctrl+Alt+Esc emergency hotkey active")
            print("[EmergencyStop] [OK] Ctrl+Alt+Esc hotkey registered")
        except Exception as e:
            print(f"[EmergencyStop] [!] Failed to register hotkey: {e}")
            self._log_event("HOTKEY_FAILED", f"Failed to register: {e}")
    
    def _emergency_trigger(self):
        """Trigger d'urgence appelé par le hotkey."""
        with self._lock:
            if self._emergency_triggered:
                return  # Déjà trigger
            
            self._emergency_triggered = True
            self._trigger_time = time.time()
            
            self._log_event("EMERGENCY_TRIGGERED", "Ctrl+Alt+Esc pressed by user")
            print("[EmergencyStop] [ALERT] EMERGENCY STOP ACTIVATED!")
            
            # Exécuter les callbacks
            for callback in self._callbacks:
                try:
                    callback()
                except Exception as e:
                    print(f"[EmergencyStop] Callback error: {e}")
            
            # Geler les actions automatisées
            self._freeze_automated_actions()
    
    def _freeze_automated_actions(self):
        """Gèle toutes les actions automatisées en cours."""
        try:
            # Arrêter pyautogui
            if PYAUTOGUI_AVAILABLE:
                pyautogui.PAUSE = 999999  # Geler les actions
            
            # Log l'action
            self._log_event("ACTIONS_FROZEN", "All automated actions paused")
            print("[EmergencyStop] [FROZEN] Automated actions frozen")
            
        except Exception as e:
            print(f"[EmergencyStop] Error freezing actions: {e}")
    
    def add_callback(self, callback: Callable[[], None]):
        """Ajoute un callback à exécuter lors de l'arrêt d'urgence."""
        with self._lock:
            self._callbacks.append(callback)
            self._log_event("CALLBACK_ADDED", f"Callback registered: {callback.__name__}")
    
    def is_emergency_active(self) -> bool:
        """Vérifie si l'arrêt d'urgence est activé."""
        with self._lock:
            return self._emergency_triggered
    
    def reset_emergency(self, reason: str = "manual"):
        """Réinitialise l'état d'urgence (nécessite une action manuelle)."""
        with self._lock:
            if not self._emergency_triggered:
                return False
            
            self._emergency_triggered = False
            self._trigger_time = None
            
            # Réactiver pyautogui
            if PYAUTOGUI_AVAILABLE:
                pyautogui.PAUSE = 0.1
            
            self._log_event("EMERGENCY_RESET", f"Emergency reset: {reason}")
            print(f"[EmergencyStop] [OK] Emergency reset ({reason})")
            return True
    
    def get_status(self) -> dict:
        """Retourne le statut actuel du système d'urgence."""
        with self._lock:
            return {
                "active": self._is_active,
                "emergency_triggered": self._emergency_triggered,
                "trigger_time": self._trigger_time,
                "hotkey_registered": self._hotkey_registered,
                "callbacks_count": len(self._callbacks),
                "keyboard_available": KEYBOARD_AVAILABLE,
                "pyautogui_available": PYAUTOGUI_AVAILABLE,
            }
    
    def _log_event(self, event_type: str, message: str):
        """Enregistre un événement dans l'audit log."""
        try:
            timestamp = datetime.now().isoformat()
            log_entry = {
                "timestamp": timestamp,
                "event_type": event_type,
                "message": message,
                "emergency_active": self._emergency_triggered,
            }
            
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
                
        except Exception as e:
            print(f"[EmergencyStop] Audit log error: {e}")
    
    def get_recent_events(self, limit: int = 10) -> list[dict]:
        """Récupère les événements récents de l'audit log."""
        try:
            if not self.audit_log_path.exists():
                return []
            
            events = []
            with open(self.audit_log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            
            # Retourner les plus récents
            return events[-limit:] if events else []
            
        except Exception as e:
            print(f"[EmergencyStop] Error reading audit log: {e}")
            return []
    
    def shutdown(self):
        """Arrête proprement le système d'urgence."""
        with self._lock:
            self._is_active = False
            
            # Désenregistrer le hotkey
            if self._hotkey_registered and KEYBOARD_AVAILABLE:
                try:
                    keyboard.remove_hotkey('ctrl+alt+esc')
                    self._hotkey_registered = False
                except Exception as e:
                    print(f"[EmergencyStop] Error removing hotkey: {e}")
            
            self._log_event("SYSTEM_SHUTDOWN", "Emergency stop system shutdown")
            print("[EmergencyStop] System shutdown complete")


# Singleton global
_EMERGENCY_STOP_SINGLETON: Optional[EmergencyStop] = None
_EMERGENCY_STOP_LOCK = threading.RLock()


def get_emergency_stop() -> EmergencyStop:
    """Retourne l'instance singleton du système d'urgence."""
    global _EMERGENCY_STOP_SINGLETON
    with _EMERGENCY_STOP_LOCK:
        if _EMERGENCY_STOP_SINGLETON is None:
            _EMERGENCY_STOP_SINGLETON = EmergencyStop()
        return _EMERGENCY_STOP_SINGLETON


def reset_emergency_stop():
    """Réinitialise le singleton (pour les tests)."""
    global _EMERGENCY_STOP_SINGLETON
    with _EMERGENCY_STOP_LOCK:
        if _EMERGENCY_STOP_SINGLETON:
            _EMERGENCY_STOP_SINGLETON.shutdown()
        _EMERGENCY_STOP_SINGLETON = None


if __name__ == "__main__":
    # Test du système d'urgence
    print("Testing Emergency Stop System...")
    emergency = get_emergency_stop()
    
    print(f"Status: {emergency.get_status()}")
    print("Press Ctrl+Alt+Esc to test emergency stop...")
    print("Press Ctrl+C to exit")
    
    try:
        while True:
            time.sleep(1)
            if emergency.is_emergency_active():
                print("Emergency detected! Resetting in 5 seconds...")
                time.sleep(5)
                emergency.reset_emergency("test")
                break
    except KeyboardInterrupt:
        print("\nShutting down...")
        emergency.shutdown()
