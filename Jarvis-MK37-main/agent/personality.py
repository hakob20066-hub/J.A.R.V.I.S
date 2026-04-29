"""
Personality engine — inject traits/tone/verbosity dans system prompt Jarvis.

Lit config/personality.yaml, expose `build_personality_suffix()` à concatener
au prompt core (core/prompt.txt).

Fallback silencieux si PyYAML absent → JSON ou defaults.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = _base_dir()
YAML_PATH       = BASE_DIR / "config" / "personality.yaml"
JSON_PATH       = BASE_DIR / "config" / "personality.json"


DEFAULT_CONFIG = {
    "active_role": "jarvis_classic",
    "roles": {
        "jarvis_classic": {
            "tone": "British butler, calls user 'sir', dry wit",
            "verbosity": "1-2 sentences",
            "humor": "subtle, rare",
            "traits": ["loyal, formal", "anticipates needs"],
        }
    },
    "global": {"language_default": "fr", "never": []},
}


def _load_raw() -> dict:
    if YAML_PATH.exists():
        try:
            import yaml  # type: ignore
            return yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or DEFAULT_CONFIG
        except Exception as e:
            print(f"[Personality] ⚠️ yaml load failed ({e}) — fallback")
    if JSON_PATH.exists():
        try:
            return json.loads(JSON_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return DEFAULT_CONFIG


def get_active_role() -> str:
    return _load_raw().get("active_role", "jarvis_classic")


def set_active_role(role: str) -> bool:
    cfg = _load_raw()
    if role not in cfg.get("roles", {}):
        return False
    cfg["active_role"] = role
    try:
        import yaml  # type: ignore
        YAML_PATH.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
    except Exception:
        JSON_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


def build_personality_suffix(role: Optional[str] = None) -> str:
    cfg    = _load_raw()
    roles  = cfg.get("roles", {})
    name   = role or cfg.get("active_role", "jarvis_classic")
    r      = roles.get(name) or next(iter(roles.values()), {})
    glob   = cfg.get("global", {})

    lines  = [f"\n\n🎭 ACTIVE ROLE: {name}"]
    if r.get("tone"):      lines.append(f"TONE: {r['tone']}")
    if r.get("verbosity"): lines.append(f"VERBOSITY: {r['verbosity']}")
    if r.get("humor"):     lines.append(f"HUMOR: {r['humor']}")
    if r.get("traits"):
        lines.append("TRAITS:")
        for t in r["traits"]:
            lines.append(f"  - {t}")
    if glob.get("never"):
        lines.append("NEVER:")
        for n in glob["never"]:
            lines.append(f"  - {n}")
    if glob.get("language_default"):
        lines.append(f"LANGUAGE DEFAULT: {glob['language_default']}")
    return "\n".join(lines) + "\n"
