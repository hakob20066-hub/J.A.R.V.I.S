"""
Bootstrap — orchestrateur du démarrage de Jarvis.

Appelé tout début de main.py. Décide :
  - Premier lancement → lance le wizard UI
  - Config incomplète (aucune clé API) → wizard
  - Config OK → continue normalement, pre-warm le LLM local

Persiste dans config/runtime.json :
  - first_launch_done: bool
  - hardware: HardwareInfo (cached)
  - last_boot: ISO timestamp
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from agent.hardware_detect import detect_hardware, save_to_runtime


# ---------- paths ----------

BASE_DIR     = Path(__file__).resolve().parent.parent
CONFIG_DIR   = BASE_DIR / "config"
RUNTIME_PATH = CONFIG_DIR / "runtime.json"
API_KEYS_PATH = CONFIG_DIR / "api_keys.json"

# Clés "minimales" : au moins UNE de celles-ci suffit pour fonctionner
# (les autres providers améliorent juste les capacités).
MINIMUM_KEYS = ["gemini_api_key", "anthropic_api_key", "openai_api_key", "groq_api_key"]


# ---------- runtime config ----------

def load_runtime() -> dict[str, Any]:
    if not RUNTIME_PATH.exists():
        return {}
    try:
        return json.loads(RUNTIME_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_runtime(data: dict[str, Any]) -> None:
    RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def mark_first_launch_done() -> None:
    rt = load_runtime()
    rt["first_launch_done"] = True
    rt["first_launch_at"] = datetime.now().isoformat(timespec="seconds")
    save_runtime(rt)


# ---------- API keys check ----------

def load_api_keys() -> dict[str, Any]:
    if not API_KEYS_PATH.exists():
        return {}
    try:
        return json.loads(API_KEYS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def has_minimum_keys() -> bool:
    """True si au moins UNE clé minimum est renseignée et non placeholder."""
    keys = load_api_keys()
    for k in MINIMUM_KEYS:
        v = keys.get(k, "")
        if isinstance(v, str) and v and not v.startswith("YOUR_"):
            return True
    return False


def is_local_only_mode() -> bool:
    """True si aucune clé cloud mais ollama dispo → mode 100% local."""
    if has_minimum_keys():
        return False
    keys = load_api_keys()
    return bool(keys.get("ollama_base_url"))


# ---------- main bootstrap ----------

def bootstrap(skip_warmup: bool = False) -> dict[str, Any]:
    """
    Returns:
        {
          "status":         "first_launch" | "configured" | "incomplete" | "local_only",
          "needs_wizard":   bool,
          "hardware":       HardwareInfo as dict,
          "warnings":       [str],
        }
    """
    rt = load_runtime()
    warnings: list[str] = []

    # 1) Détection hardware (cache si déjà fait)
    if "hardware" not in rt:
        info = detect_hardware()
        save_to_runtime(info, RUNTIME_PATH)
        rt = load_runtime()  # reload après save
    hw = rt.get("hardware", {})

    # 2) Détermine status
    first_launch = not rt.get("first_launch_done", False)
    has_keys = has_minimum_keys()
    local_only = is_local_only_mode()

    if first_launch:
        status = "first_launch"
        needs_wizard = True
    elif has_keys:
        status = "configured"
        needs_wizard = False
    elif local_only:
        status = "local_only"
        needs_wizard = False
        warnings.append(
            "Mode 100% local : voies cloud désactivées (Voie 1 fast, Voie 2 deep). "
            "Seule la Voie 4 (qwen abliterate) est active. "
            "Ajoute au moins une clé cloud pour activer les autres voies."
        )
    else:
        status = "incomplete"
        needs_wizard = True
        warnings.append("Aucune clé API trouvée. Lance le wizard pour configurer.")

    # 3) Pre-warm provider local en thread BG (sauf 1er lancement)
    if not first_launch and not skip_warmup:
        threading.Thread(
            target=_warmup_local_provider_bg,
            daemon=True,
            name="local-warmup",
        ).start()

    # 4) Update last_boot
    rt["last_boot"] = datetime.now().isoformat(timespec="seconds")
    save_runtime(rt)

    return {
        "status":       status,
        "needs_wizard": needs_wizard,
        "hardware":     hw,
        "warnings":     warnings,
    }


def _warmup_local_provider_bg() -> None:
    """Lazy import pour ne pas charger les deps si pas appelé."""
    try:
        from agent.local_llm_provider import get_local_provider
        get_local_provider().warmup()
    except Exception as e:
        print(f"[Bootstrap] ⚠️ Local warmup background failed: {e}")


# ---------- CLI ----------

if __name__ == "__main__":
    result = bootstrap(skip_warmup=True)
    print("🚀 Bootstrap result:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
