from __future__ import annotations

import json
import platform
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Optional

import webview

from agent.bootstrap import mark_first_launch_done, load_runtime, save_runtime
from agent.hardware_detect import HardwareInfo, detect_hardware, recommend_backend
from agent.llm_router import validate_provider_key
from agent.local_llm_provider import ensure_model_installed
from agent.voice_router import process as voice_process, _get_voice
from config.secure_api_keys import load_api_config, save_api_config


BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
API_KEYS_PATH = CONFIG_DIR / "api_keys.json"
HTML_PATH = BASE_DIR / "ui_wizard.html"

API_FIELDS = [
    "gemini_api_key",
    "anthropic_api_key",
    "openai_api_key",
    "groq_api_key",
    "deepseek_api_key",
    "openrouter_api_key",
    "venice_api_key",
    "kindo_api_key",
    "hackergpt_api_key",
    "cerebras_api_key",
    "mistral_api_key",
    "huggingface_api_key",
    "intelx_api_key",
]


@dataclass
class InstallProgress:
    running: bool = False
    completed: bool = False
    progress: float = 0.0
    message: str = ""
    error: str = ""
    logs: list[str] = field(default_factory=list)


class WizardApi:
    def __init__(self) -> None:
        self.model_priority: str = "performance"
        self.hardware: HardwareInfo = detect_hardware(priority=self.model_priority)
        self.progress = InstallProgress()
        self._lock = threading.Lock()

    def get_hardware(self) -> Dict[str, object]:
        data = asdict(self.hardware)
        data["justification"] = self._build_justification(self.hardware)
        data["model_priority"] = self.model_priority
        return data

    def get_api_schema(self) -> list[str]:
        return API_FIELDS

    def set_model_priority(self, priority: str) -> Dict[str, object]:
        selected = (priority or "performance").strip().lower()
        if selected not in ("performance", "quality"):
            selected = "performance"
        self.model_priority = selected
        backend, model = recommend_backend(
            self.hardware.vram_gb,
            ram_gb=self.hardware.ram_gb,
            priority=selected,
        )
        self.hardware.recommended_local_backend = backend
        self.hardware.recommended_local_model = model
        runtime = load_runtime()
        runtime["model_priority"] = selected
        runtime["local_backend_override"] = backend
        runtime["local_model_override"] = model
        save_runtime(runtime)
        return self.get_hardware()

    def start_model_install(self) -> Dict[str, object]:
        with self._lock:
            if self.progress.running:
                return self._progress_dict()
            self.progress = InstallProgress(running=True, message="🟢[FAST] Preparing install")
        runtime = load_runtime()
        runtime["local_llm_enabled"] = True
        runtime["model_priority"] = self.model_priority
        runtime["local_backend_override"] = self.hardware.recommended_local_backend
        runtime["local_model_override"] = self.hardware.recommended_local_model
        save_runtime(runtime)
        threading.Thread(target=self._install_worker, daemon=True, name="wizard-model-install").start()
        return self._progress_dict()

    def skip_local_install(self) -> Dict[str, object]:
        runtime = load_runtime()
        runtime["local_llm_enabled"] = False
        save_runtime(runtime)
        with self._lock:
            self.progress.running = False
            self.progress.completed = True
            self.progress.progress = 100.0
            self.progress.message = "🟢[FAST] Local LLM skipped. Cloud-only mode enabled."
            self.progress.logs.append(self.progress.message)
        return self._progress_dict()

    def get_install_status(self) -> Dict[str, object]:
        with self._lock:
            return self._progress_dict()

    def test_api_key(self, provider: str, value: str) -> Dict[str, object]:
        ok, message = validate_provider_key(provider, value)
        log = f"🟣[MISSION] API key test {provider}: {message}"
        with self._lock:
            self.progress.logs.append(log)
        return {"ok": ok, "message": message}

    def save_api_keys(
        self,
        values: Dict[str, str],
        encrypt_enabled: bool = False,
        master_password: str = "",
    ) -> Dict[str, object]:
        existing: Dict[str, object] = {}
        loaded = load_api_config(API_KEYS_PATH, prompt_if_encrypted=False)
        if loaded.loaded:
            existing = loaded.data

        payload: Dict[str, object] = dict(existing)
        for key in API_FIELDS:
            payload[key] = (values.get(key, "") or "").strip()
        payload["os_system"] = self._detect_os()
        payload.setdefault("ollama_base_url", "http://localhost:11434")

        pwd = (master_password or "").strip() if encrypt_enabled else ""
        if encrypt_enabled and not pwd:
            return {"ok": False, "saved": 0, "error": "Master password required for encryption."}
        save_api_config(payload, path=API_KEYS_PATH, master_password=pwd)
        return {"ok": True, "saved": len(API_FIELDS)}

    def run_ttft_test(self, prompt: str) -> Dict[str, object]:
        # Step 4 = TTFT de la VOIE 4 (uncensored). On force voie 4 directement
        # au lieu de passer par le classifier — sinon une question banale
        # serait routée vers voie 1 et le test ne validerait jamais voie 4.
        t0 = time.perf_counter()
        try:
            voice4 = _get_voice(4)
            response = voice4.process(prompt or "Say hello in one short sentence.", None)
        except Exception as e:
            return {
                "ok": False,
                "ttft_ms": int((time.perf_counter() - t0) * 1000),
                "voice_id": 4,
                "provider": "error",
                "preview": f"Voie 4 indisponible: {e}",
            }
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        preview = (response.text or "").strip()[:200]
        ok = bool(preview) and response.provider_used != "error" and " error]" not in preview.lower()
        return {
            "ok": ok,
            "ttft_ms": elapsed_ms,
            "voice_id": response.voice_id,
            "provider": response.provider_used,
            "preview": preview,
        }

    def close_window(self) -> Dict[str, object]:
        """Ferme la fenêtre wizard côté Python (window.close() JS est bloqué)."""
        try:
            for w in webview.windows:
                w.destroy()
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True}

    def complete(self) -> Dict[str, object]:
        runtime = load_runtime()
        runtime.setdefault("local_llm_enabled", True)
        runtime["model_priority"] = self.model_priority
        runtime["local_backend_override"] = self.hardware.recommended_local_backend
        runtime["local_model_override"] = self.hardware.recommended_local_model
        save_runtime(runtime)
        mark_first_launch_done()
        return {"ok": True}

    def _install_worker(self) -> None:
        def on_progress(value: float, message: str) -> None:
            with self._lock:
                self.progress.progress = value
                self.progress.message = message
                self.progress.logs.append(message)

        try:
            ensure_model_installed(on_progress=on_progress)
            with self._lock:
                self.progress.running = False
                self.progress.completed = True
                self.progress.progress = 100.0
                self.progress.message = "🟢[FAST] Model install complete"
        except Exception as e:
            with self._lock:
                self.progress.running = False
                self.progress.error = str(e)
                self.progress.message = "🔴[UNCENSORED] Model install failed"
                self.progress.logs.append(f"🔴[UNCENSORED] {e}")

    def _progress_dict(self) -> Dict[str, object]:
        return {
            "running": self.progress.running,
            "completed": self.progress.completed,
            "progress": self.progress.progress,
            "message": self.progress.message,
            "error": self.progress.error,
            "logs": self.progress.logs[-50:],
        }

    @staticmethod
    def _build_justification(hw: HardwareInfo) -> str:
        if hw.vram_gb >= 24:
            return "🔵[DEEP] VRAM >= 24GB: Ollama + qwen2.5:72b for max quality."
        if hw.vram_gb >= 12:
            return "🔵[DEEP] VRAM 12-23GB: AirLLM + Qwen/Qwen2.5-72B-Instruct for big model compatibility."
        if hw.vram_gb >= 6:
            return "🟢[FAST] VRAM 6-11GB: Ollama + qwen2.5:14b for balanced speed."
        if "14b" in (hw.recommended_local_model or "").lower():
            return "🔵[DEEP] Quality mode: 14B suggested via RAM offloading on borderline VRAM."
        return "🟢[FAST] VRAM < 6GB/iGPU/CPU: Ollama + llama3.2:3b for low latency."

    @staticmethod
    def _detect_os() -> str:
        system_name = platform.system().lower()
        if system_name == "darwin":
            return "mac"
        if system_name == "windows":
            return "windows"
        return "linux"


def run() -> None:
    if not HTML_PATH.exists():
        raise FileNotFoundError(f"Wizard HTML missing: {HTML_PATH}")
    html = HTML_PATH.read_text(encoding="utf-8")
    api = WizardApi()
    window = webview.create_window(
        "Jarvis MK37 Setup Wizard",
        html=html,
        js_api=api,
        fullscreen=True,
        background_color="#0b0f16",
    )
    webview.start(debug=False)
    if window:
        return
