"""
Working memory — RAM-only, FIFO court-terme (session courante).

Garde les N derniers tours (user/assistant/tool) pour donner du contexte au LLM.
Pas de persistence : reset à chaque redémarrage de Jarvis (par design).

FIFO : quand taille > MAX_TURNS, les plus anciens sont dropés.

Usage :
    wm = get_working_memory()
    wm.add_turn("user", "Salut", intent="greeting")
    wm.add_turn("assistant", "Hey!")
    ctx = wm.recent_turns(n=10)        # liste des 10 derniers
    s = wm.format_for_prompt()         # formaté pour injection
    
Métadonnées optionnelles :
    - intent: intentionnalité détectée
    - entities: [liste d'entités NER]
    - confidence: score (0..1)
    - action: action exécutée
    - result: résultat de l'action
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Optional


DEFAULT_MAX_TURNS = 20


@dataclass
class Turn:
    role:      str                # "user" | "assistant" | "tool" | "system" | "action"
    content:   str
    timestamp: float = field(default_factory=time.time)
    metadata:  dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Sérialise en dict."""
        return asdict(self)
    
    @staticmethod
    def from_dict(d: dict) -> Turn:
        """Désérialise depuis dict."""
        return Turn(
            role=d.get("role", ""),
            content=d.get("content", ""),
            timestamp=d.get("timestamp", time.time()),
            metadata=d.get("metadata", {}),
        )


class WorkingMemory:

    def __init__(self, max_turns: int = DEFAULT_MAX_TURNS):
        self.max_turns = max_turns
        self._turns: deque[Turn] = deque(maxlen=max_turns)
        self._lock = threading.RLock()

    def add_turn(self, role: str, content: str, **metadata) -> Turn:
        turn = Turn(role=role, content=content, metadata=metadata or {})
        with self._lock:
            self._turns.append(turn)
        return turn

    def recent_turns(self, n: Optional[int] = None) -> list[Turn]:
        with self._lock:
            if n is None or n >= len(self._turns):
                return list(self._turns)
            return list(self._turns)[-n:]

    def get_all(self) -> list[Turn]:
        """Retourne tous les turns (alias pour recent_turns avec n=None)."""
        return self.recent_turns(n=None)

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._turns)

    def format_for_prompt(self, n: Optional[int] = None, max_chars: int = 2000) -> str:
        """Renvoie un texte court à injecter dans un system prompt."""
        turns = self.recent_turns(n)
        if not turns:
            return ""
        lines = []
        for t in turns:
            content = t.content if len(t.content) < 300 else t.content[:300] + "…"
            lines.append(f"{t.role}: {content}")
        text = "\n".join(lines)
        if len(text) > max_chars:
            text = text[-max_chars:]
        return text

    def to_dicts(self) -> list[dict]:
        with self._lock:
            return [t.to_dict() for t in self._turns]
    
    def to_json(self) -> str:
        """Sérialise en JSON."""
        with self._lock:
            return json.dumps([t.to_dict() for t in self._turns], ensure_ascii=False, indent=2)
    
    @staticmethod
    def from_json(data: str) -> WorkingMemory:
        """Désérialise depuis JSON."""
        wm = WorkingMemory()
        try:
            turns = json.loads(data)
            for t in turns:
                wm.add_turn(
                    role=t.get("role", ""),
                    content=t.get("content", ""),
                    **t.get("metadata", {}),
                )
        except Exception:
            pass
        return wm


# ---------- singleton ----------

_WM_SINGLETON: Optional[WorkingMemory] = None


def get_working_memory() -> WorkingMemory:
    global _WM_SINGLETON
    if _WM_SINGLETON is None:
        _WM_SINGLETON = WorkingMemory()
    return _WM_SINGLETON


def reset_working_memory() -> None:
    global _WM_SINGLETON
    _WM_SINGLETON = None
