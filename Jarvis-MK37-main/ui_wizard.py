from __future__ import annotations

import json
import platform
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Optional

import webview

from agent.bootstrap import mark_first_launch_done
from agent.hardware_detect import HardwareInfo, detect_hardware
from agent.llm_router import validate_provider_key
from agent.local_llm_provider import ensure_model_installed
from agent.voice_router import process as voice_process


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
        self.hardware: HardwareInfo = detect_hardware()
        self.progress = InstallProgress()
        self._lock = threading.Lock()

    def get_hardware(self) -> Dict[str, object]:
        data = asdict(self.hardware)
        data["justification"] = self._build_justification(self.hardware)
        return data

    def get_api_schema(self) -> list[str]:
        return API_FIELDS

    def start_model_install(self) -> Dict[str, object]:
        with self._lock:
            if self.progress.running:
                return self._progress_dict()
            self.progress = InstallProgress(running=True, message="🟢[FAST] Preparing install")
        threading.Thread(target=self._install_worker, daemon=True, name="wizard-model-install").start()
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

    def save_api_keys(self, values: Dict[str, str]) -> Dict[str, object]:
        existing: Dict[str, object] = {}
        if API_KEYS_PATH.exists():
            try:
                existing = json.loads(API_KEYS_PATH.read_text(encoding="utf-8"))
            except Exception:
                existing = {}

        payload: Dict[str, object] = dict(existing)
        for key in API_FIELDS:
            payload[key] = (values.get(key, "") or "").strip()
        payload["os_system"] = self._detect_os()
        payload.setdefault("ollama_base_url", "http://localhost:11434")

        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        API_KEYS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"ok": True, "saved": len(API_FIELDS)}

    def run_ttft_test(self, prompt: str) -> Dict[str, object]:
        t0 = time.perf_counter()
        response = voice_process(prompt or "Say hello in one short sentence.")
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        preview = (response.text or "").strip()[:200]
        return {
            "ok": bool(preview),
            "ttft_ms": elapsed_ms,
            "voice_id": response.voice_id,
            "provider": response.provider_used,
            "preview": preview,
        }

    def complete(self) -> Dict[str, object]:
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
            return "🔵[DEEP] VRAM >= 24GB: Ollama + qwen2.5-72b-abliterate for max quality."
        if hw.vram_gb >= 12:
            return "🔵[DEEP] VRAM 12-23GB: AirLLM + qwen2.5-72b-abliterate for big model compatibility."
        if hw.vram_gb >= 6:
            return "🟢[FAST] VRAM 6-11GB: Ollama + qwen2.5-abliterate:14b for balanced speed."
        return "🟢[FAST] VRAM < 6GB/iGPU/CPU: Ollama + llama3.2-3b-instruct-abliterated for low latency."

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
