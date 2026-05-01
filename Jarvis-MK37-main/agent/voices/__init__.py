"""
Voices — les 4 voies cognitives de Jarvis.

  Voie 1 (FAST)       : Groq/Cerebras direct, < 2s, pas de specialists
  Voie 2 (DEEP)       : Claude/Gemini supervise specialists (code/research/etc)
  Voie 3 (MISSION)    : async background (mission_runner)
  Voie 4 (UNCENSORED) : qwen2.5-abliterate local supervise specialists raw

Chaque voix implémente le protocole `Voice` (voir voices/base.py).
"""

from agent.voices.base import Voice, VoiceResponse  # noqa: F401
