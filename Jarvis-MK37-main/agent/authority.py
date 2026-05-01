"""
Authority Engine — gating des actions sensibles + audit trail.

Chaque tool call passe par `check(tool, parameters)` qui retourne :
  ("allow", reason)     → exécuter librement
  ("ask", reason)       → demander confirmation (via callback)
  ("deny", reason)      → bloquer

Politique configurable via config/authority.json :
{
  "mode": "balanced",   // paranoid | balanced | autonomous
  "allowlist": ["web_search", "weather_report", ...],
  "denylist": [],
  "ask_for":   ["shutdown_jarvis", "file_controller:delete", "computer_settings"],
  "auto_approve_patterns": []
}

Audit trail : memory/authority_audit.log (JSONL).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from threading import Lock
from typing import Callable, Optional


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR    = _base_dir()
CONFIG_PATH = BASE_DIR / "config" / "authority.json"
AUDIT_PATH  = BASE_DIR / "memory" / "authority_audit.log"
_lock       = Lock()


DEFAULT_POLICY = {
    "mode": "balanced",
    "allowlist": [
        "web_search", "weather_report", "youtube_video",
        "screen_process", "flight_finder", "reminder",
    ],
    "denylist": [],
    "ask_for": [
        "shutdown_jarvis",
        "file_controller:delete",
        "file_controller:move",
        "computer_settings",
        "computer_control:hotkey",
        "desktop_control:clean",
        "game_updater:install",
        "send_message",
        "generated_code",
    ],
    "auto_approve_patterns": [],
    # Tools "speech-only" : pure parole/lecture, jamais filtrés.
    # La parole est libre — seules les ACTIONS sont gated.
    "speech_only_tools": [
        "tell_user", "say", "speak",
        "query_memory", "search_memory", "recall",
        "web_search", "scrape_url",   # read-only web
        "read_file", "list_files",     # read-only fs
        "describe_screen", "ocr_screen",
        "generate_text", "summarize", "translate",
        "classify", "embed",
    ],
}


def _load_policy() -> dict:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(DEFAULT_POLICY, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return DEFAULT_POLICY
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_POLICY


def _audit(event: dict) -> None:
    try:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _lock, open(AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), **event}, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[Authority] ⚠️ audit write failed: {e}")


class Authority:
    def __init__(self, ask_fn: Optional[Callable[[str, dict], bool]] = None):
        """
        ask_fn(tool, params) -> bool : callback utilisé quand 'ask' nécessaire.
        Si None : auto-approve en mode autonomous, refuse sinon.
        """
        self.policy = _load_policy()
        self.ask_fn = ask_fn

    def reload(self) -> None:
        self.policy = _load_policy()

    def is_speech_only(self, tool: str) -> bool:
        """True si le tool est pur 'parole' (pas d'action sur le système)."""
        return tool in self.policy.get("speech_only_tools", [])

    def check(self, tool: str, parameters: dict) -> tuple[str, str]:
        mode   = self.policy.get("mode", "balanced")
        action = parameters.get("action")
        qkey   = f"{tool}:{action}" if action else tool

        # Speech-only : toujours allow, audit log de niveau "speech"
        if self.is_speech_only(tool):
            _audit({
                "decision": "allow", "tool": tool, "action": action,
                "mode": mode, "level": "speech",
            })
            return ("allow", "speech-only")

        # Denylist : priorité absolue
        if tool in self.policy.get("denylist", []) or qkey in self.policy.get("denylist", []):
            return ("deny", f"denylisted ({qkey})")

        # Autonomous : presque tout passe
        if mode == "autonomous":
            _audit({"decision": "allow", "tool": tool, "action": action,
                    "mode": mode, "level": "action"})
            return ("allow", "autonomous")

        # Allowlist : pass-through
        if tool in self.policy.get("allowlist", []):
            _audit({"decision": "allow", "tool": tool, "action": action,
                    "mode": mode, "level": "action"})
            return ("allow", "allowlisted")

        # Ask-for : demande confirm
        ask_list = self.policy.get("ask_for", [])
        if tool in ask_list or qkey in ask_list or mode == "paranoid":
            return ("ask", f"sensitive ({qkey})")

        # Par défaut : allow en balanced
        if mode == "balanced":
            _audit({"decision": "allow", "tool": tool, "action": action,
                    "mode": mode, "level": "action"})
            return ("allow", "balanced-default")

        return ("ask", "unknown-default")

    def authorize(self, tool: str, parameters: dict) -> bool:
        """True si exécution permise, False sinon."""
        verdict, reason = self.check(tool, parameters)
        action = parameters.get("action")

        if verdict == "allow":
            return True

        if verdict == "deny":
            _audit({"decision": "deny", "tool": tool, "action": action,
                    "reason": reason, "level": "action"})
            print(f"[Authority] 🚫 deny {tool} ({reason})")
            return False

        # verdict == "ask"
        if self.ask_fn is None:
            auto = self.policy.get("mode") == "autonomous"
            _audit({
                "decision": "allow" if auto else "deny",
                "tool": tool, "action": action,
                "reason": f"{reason} no-ask-fn", "level": "action",
            })
            return auto

        try:
            ok = bool(self.ask_fn(tool, parameters))
        except Exception as e:
            print(f"[Authority] ⚠️ ask_fn error: {e}")
            ok = False

        _audit({
            "decision": "allow" if ok else "deny",
            "tool": tool, "action": action,
            "reason": f"user:{reason}", "level": "action",
        })
        return ok


_AUTH_SINGLETON: Optional[Authority] = None


def get_authority(ask_fn: Optional[Callable[[str, dict], bool]] = None) -> Authority:
    global _AUTH_SINGLETON
    if _AUTH_SINGLETON is None:
        _AUTH_SINGLETON = Authority(ask_fn=ask_fn)
    elif ask_fn is not None:
        _AUTH_SINGLETON.ask_fn = ask_fn
    return _AUTH_SINGLETON
