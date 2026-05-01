"""
Base class pour les 4 voix cognitives.

Une voix reçoit (query, context) et retourne une VoiceResponse.
Les voix 2 et 4 surveillent leurs specialists ; voix 1 répond direct ;
voix 3 schedule async (gérée séparément par mission_runner).
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VoiceResponse:
    text:               str
    voice_id:           int                          # 1, 2, 3 ou 4
    provider_used:      str                          # ex "anthropic", "ollama"
    specialists_called: list[str] = field(default_factory=list)
    refusal_detected:   bool = False
    elapsed_seconds:    float = 0.0
    raw_outputs:        list[str] = field(default_factory=list)  # avant synthèse
    metadata:           dict = field(default_factory=dict)


class Voice(ABC):
    """Interface commune. Implémentations dans voice_fast/deep/uncensored.py."""

    voice_id:    int = 0
    name:        str = "base"
    description: str = ""

    @abstractmethod
    def process(self, query: str, context: Optional[dict] = None) -> VoiceResponse:
        """Traite la query et retourne la réponse synthétisée."""
        ...

    # ---------- helpers communs ----------

    def _start_timer(self) -> float:
        return time.time()

    def _build_response(self, text: str, start: float, **kw) -> VoiceResponse:
        return VoiceResponse(
            text=text,
            voice_id=self.voice_id,
            provider_used=kw.pop("provider_used", "unknown"),
            specialists_called=kw.pop("specialists_called", []),
            refusal_detected=kw.pop("refusal_detected", False),
            elapsed_seconds=round(time.time() - start, 3),
            raw_outputs=kw.pop("raw_outputs", []),
            metadata=kw.pop("metadata", {}),
        )

    def _log(self, msg: str) -> None:
        print(f"[Voice{self.voice_id}/{self.name}] {msg}")
