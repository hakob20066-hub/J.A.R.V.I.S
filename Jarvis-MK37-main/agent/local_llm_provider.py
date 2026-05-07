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
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Protocol

from agent.hardware_detect import HardwareInfo, detect_hardware, load_from_runtime
from config.secure_api_keys import load_api_config


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
    def ensure_model_installed(self, on_progress: Optional[Callable[[float, str], None]] = None) -> None: ...


@dataclass
class InstallStatus:
    success: bool
    backend: str
    model: str
    message: str = ""


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

    def is_model_installed(self) -> bool:
        """True si `self.model` est déjà dans la liste ollama (pas de pull nécessaire)."""
        try:
            import requests
            r = requests.get(f"{self.base_url}/api/tags", timeout=2)
            if r.status_code != 200:
                return False
            installed = {m.get("name", "") for m in r.json().get("models", [])}
            # Match exact ou avec/sans tag :latest
            target = self.model
            if target in installed:
                return True
            if ":" not in target and f"{target}:latest" in installed:
                return True
            return False
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

    def ensure_model_installed(self, on_progress: Optional[Callable[[float, str], None]] = None) -> None:
        if on_progress:
            on_progress(0.0, f"🟢[FAST] Checking local model {self.model}")
        try:
            proc = subprocess.Popen(
                ["ollama", "pull", self.model],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as e:
            raise RuntimeError(f"🟢[FAST] Unable to start ollama pull: {e}") from e

        if proc.stdout is not None:
            for line in proc.stdout:
                clean = _clean_ollama_output(line)
                if not clean:
                    continue
                progress = _extract_ollama_progress(clean)
                if on_progress and progress is not None:
                    on_progress(progress, f"🟢[FAST] {clean}")
                elif on_progress:
                    on_progress(0.0, f"🟢[FAST] {clean}")
        code = proc.wait()
        if code != 0:
            raise RuntimeError(f"🟢[FAST] ollama pull failed for {self.model}")
        if on_progress:
            on_progress(100.0, f"🟢[FAST] Model ready: {self.model}")

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

    def ensure_model_installed(self, on_progress: Optional[Callable[[float, str], None]] = None) -> None:
        if on_progress:
            on_progress(0.0, "🔵[DEEP] Installing AirLLM runtime")
        try:
            proc = subprocess.Popen(
                ["python", "-m", "pip", "install", "airllm"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as e:
            raise RuntimeError(f"🔵[DEEP] Unable to launch pip install airllm: {e}") from e

        if proc.stdout is not None:
            for line in proc.stdout:
                clean = line.strip()
                if not clean:
                    continue
                if on_progress:
                    on_progress(50.0, f"🔵[DEEP] {clean}")
        code = proc.wait()
        if code != 0:
            raise RuntimeError("🔵[DEEP] pip install airllm failed")
        if on_progress:
            on_progress(100.0, "🔵[DEEP] AirLLM runtime ready")

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
LEGACY_MODEL_ALIASES = {
    "llama3.2-3b-instruct-abliterated": "llama3.2:3b",
    "qwen2.5-abliterate:14b": "qwen2.5:14b",
    "qwen2.5-72b-abliterate": "qwen2.5:72b",
}


def _resolve_runtime_path() -> Path:
    global _RUNTIME_PATH
    if _RUNTIME_PATH is None:
        _RUNTIME_PATH = Path(__file__).resolve().parent.parent / "config" / "runtime.json"
    return _RUNTIME_PATH


def _load_ollama_base_url() -> str:
    """Lit ollama_base_url depuis api_keys.json si dispo, sinon défaut."""
    cfg_path = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
    loaded = load_api_config(cfg_path, prompt_if_encrypted=True)
    if loaded.loaded:
        return str(loaded.data.get("ollama_base_url", "http://localhost:11434"))
    return "http://localhost:11434"


def _extract_ollama_progress(line: str) -> Optional[float]:
    parts = line.split("%")
    if not parts:
        return None
    prefix = parts[0].strip().split(" ")
    if not prefix:
        return None
    try:
        value = float(prefix[-1].replace("%", ""))
    except Exception:
        return None
    if value < 0:
        return 0.0
    if value > 100:
        return 100.0
    return value


def _clean_ollama_output(line: str) -> str:
    clean = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", line or "")
    clean = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", clean)
    return clean.strip()


def normalize_model_name(model: str) -> str:
    """Map old experimental names to installable model identifiers."""
    cleaned = (model or "").strip()
    return LEGACY_MODEL_ALIASES.get(cleaned, cleaned)


def get_local_provider(force_redetect: bool = False) -> LocalLLMProvider:
    """Singleton. Choisit le backend selon hardware_detect (cached dans runtime.json)."""
    global _PROVIDER_SINGLETON

    if _PROVIDER_SINGLETON is not None and not force_redetect:
        return _PROVIDER_SINGLETON

    runtime_path = _resolve_runtime_path()
    runtime_data: dict = {}
    if runtime_path.exists():
        try:
            runtime_data = json.loads(runtime_path.read_text(encoding="utf-8"))
        except Exception:
            runtime_data = {}

    if runtime_data.get("local_llm_enabled") is False:
        _PROVIDER_SINGLETON = OllamaProvider(
            model="llama3.2:3b",
            base_url=_load_ollama_base_url(),
        )
        print("[Local] 🟢[FAST] local_llm_enabled=false -> lightweight placeholder provider")
        return _PROVIDER_SINGLETON

    info = load_from_runtime(runtime_path)

    if info is None or force_redetect:
        priority = str(runtime_data.get("model_priority", "performance"))
        info = detect_hardware(priority=priority)

    override_backend = str(runtime_data.get("local_backend_override", "")).strip().lower()
    override_model = str(runtime_data.get("local_model_override", "")).strip()
    if override_backend in ("ollama", "airllm"):
        info.recommended_local_backend = override_backend
    if override_model:
        info.recommended_local_model = normalize_model_name(override_model)

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


def ensure_model_installed(
    force_redetect: bool = False,
    on_progress: Optional[Callable[[float, str], None]] = None,
) -> InstallStatus:
    provider = get_local_provider(force_redetect=force_redetect)
    provider.ensure_model_installed(on_progress=on_progress)
    return InstallStatus(
        success=True,
        backend=provider.backend,
        model=provider.model,
        message="Model installation completed.",
    )
