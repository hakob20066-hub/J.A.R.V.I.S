"""
Local LLM Provider — abstraction unifiée Ollama / AirLLM.

Le LLM Router (agent/llm_router.py) appelle get_local_provider() au lieu d'un
backend hardcodé. Le provider est choisi par hardware_detect.py au boot et
mémorisé dans config/runtime.json.

Backends:
  - OllamaProvider     : http://localhost:11434, modèles légers (8B-72B selon GPU)
  - AirLLMProvider     : layer-by-layer swap, gros modèles (70B+) sur petit GPU

Première requête : warmup automatique (charge le modèle en mémoire).
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Optional, Protocol

from agent.hardware_detect import HardwareInfo, detect_hardware, load_from_runtime


# ---------- protocol ----------

class LocalLLMProvider(Protocol):
    backend: str
    model:   str

    def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str: ...

    def is_available(self) -> bool: ...
    def warmup(self) -> None: ...


# ---------- Ollama ----------

class OllamaProvider:
    backend = "ollama"

    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self.model    = model
        self.base_url = base_url
        self._warmed  = False
        self._lock    = threading.Lock()

    def is_available(self) -> bool:
        try:
            import requests
            r = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def warmup(self) -> None:
        with self._lock:
            if self._warmed:
                return
            if not self.is_available():
                print(f"[Local] ⚠️ Ollama unreachable at {self.base_url}")
                return
            print(f"[Local] 🔥 Warming Ollama '{self.model}'...")
            try:
                self.generate("hi", max_tokens=4)
                self._warmed = True
                print(f"[Local] ✅ Ollama warmed.")
            except Exception as e:
                print(f"[Local] ⚠️ Ollama warmup failed: {e}")

    def generate(self, prompt, system="", temperature=0.7, max_tokens=4096) -> str:
        import requests
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system or "",
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        r = requests.post(f"{self.base_url}/api/generate", json=payload, timeout=300)
        r.raise_for_status()
        return (r.json().get("response") or "").strip()


# ---------- AirLLM ----------

class AirLLMProvider:
    """
    AirLLM permet de faire tourner du 70B+ sur petit GPU (4-12 GB) en swappant
    les couches une par une. ATTENTION : très lent (1 token / 30-60s).
    À réserver aux missions async, pas au voice loop temps réel.
    """
    backend = "airllm"

    def __init__(self, model: str, compression: str = "4bit"):
        self.model       = model
        self.compression = compression
        self._airllm_model = None
        self._tokenizer    = None
        self._warmed       = False
        self._lock         = threading.Lock()

    def is_available(self) -> bool:
        try:
            import importlib
            importlib.import_module("airllm")
            return True
        except Exception:
            return False

    def warmup(self) -> None:
        with self._lock:
            if self._warmed:
                return
            if not self.is_available():
                print("[Local] ⚠️ AirLLM not installed (pip install airllm).")
                return
            print(f"[Local] 🔥 Loading AirLLM '{self.model}' (peut prendre 1-3 min)...")
            t0 = time.time()
            try:
                from airllm import AutoModel
                self._airllm_model = AutoModel.from_pretrained(
                    self.model,
                    compression=self.compression,
                )
                self._warmed = True
                print(f"[Local] ✅ AirLLM loaded in {time.time()-t0:.1f}s.")
            except Exception as e:
                print(f"[Local] ❌ AirLLM load failed: {e}")

    def generate(self, prompt, system="", temperature=0.7, max_tokens=512) -> str:
        if not self._warmed:
            self.warmup()
        if self._airllm_model is None:
            raise RuntimeError("AirLLM not loaded.")

        full_prompt = (system + "\n\n" + prompt).strip() if system else prompt
        input_tokens = self._airllm_model.tokenizer(
            full_prompt,
            return_tensors="pt",
            return_attention_mask=False,
            truncation=True,
            max_length=2048,
        )
        out = self._airllm_model.generate(
            input_tokens["input_ids"],
            max_new_tokens=max_tokens,
            use_cache=True,
            return_dict_in_generate=True,
            temperature=temperature,
        )
        text = self._airllm_model.tokenizer.decode(out.sequences[0], skip_special_tokens=True)
        # Strip le prompt initial
        return text.replace(full_prompt, "").strip()


# ---------- factory ----------

_PROVIDER_SINGLETON: Optional[LocalLLMProvider] = None
_RUNTIME_PATH: Optional[Path] = None


def _resolve_runtime_path() -> Path:
    global _RUNTIME_PATH
    if _RUNTIME_PATH is None:
        _RUNTIME_PATH = Path(__file__).resolve().parent.parent / "config" / "runtime.json"
    return _RUNTIME_PATH


def _load_ollama_base_url() -> str:
    """Lit ollama_base_url depuis api_keys.json si dispo, sinon défaut."""
    cfg_path = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            return cfg.get("ollama_base_url", "http://localhost:11434")
        except Exception:
            pass
    return "http://localhost:11434"


def get_local_provider(force_redetect: bool = False) -> LocalLLMProvider:
    """Singleton. Choisit le backend selon hardware_detect (cached dans runtime.json)."""
    global _PROVIDER_SINGLETON

    if _PROVIDER_SINGLETON is not None and not force_redetect:
        return _PROVIDER_SINGLETON

    runtime_path = _resolve_runtime_path()
    info = load_from_runtime(runtime_path)

    if info is None or force_redetect:
        info = detect_hardware()

    if info.recommended_local_backend == "airllm":
        _PROVIDER_SINGLETON = AirLLMProvider(model=info.recommended_local_model)
    else:
        _PROVIDER_SINGLETON = OllamaProvider(
            model=info.recommended_local_model,
            base_url=_load_ollama_base_url(),
        )

    print(f"[Local] 🧠 Provider: {_PROVIDER_SINGLETON.backend} / {_PROVIDER_SINGLETON.model}")
    return _PROVIDER_SINGLETON


def reset_provider() -> None:
    """Force re-init au prochain get_local_provider() (tests, hot-reload config)."""
    global _PROVIDER_SINGLETON
    _PROVIDER_SINGLETON = None
