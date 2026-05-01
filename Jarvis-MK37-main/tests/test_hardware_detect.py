"""Tests pour agent/hardware_detect.py."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# Permettre import depuis racine projet
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.hardware_detect import (  # noqa: E402
    HardwareInfo, detect_hardware, recommend_backend,
    save_to_runtime, load_from_runtime,
    VRAM_THRESHOLD_AIRLLM, VRAM_THRESHOLD_OLLAMA_70B,
)


# ---------- recommend_backend ----------

def test_recommend_backend_high_vram_uses_ollama_70b():
    backend, model = recommend_backend(vram_gb=24.0)
    assert backend == "ollama"
    assert "72b" in model.lower() or "70b" in model.lower()


def test_recommend_backend_mid_vram_uses_airllm():
    backend, model = recommend_backend(vram_gb=12.0)
    assert backend == "airllm"


def test_recommend_backend_low_vram_uses_ollama_small():
    backend, model = recommend_backend(vram_gb=4.0)
    assert backend == "ollama"
    assert "3b" in model.lower()


def test_recommend_backend_zero_vram_uses_ollama_small():
    backend, model = recommend_backend(vram_gb=0.0)
    assert backend == "ollama"
    assert "3b" in model.lower()


def test_recommend_backend_threshold_boundaries():
    # Juste en dessous du seuil 70B → AirLLM
    backend, _ = recommend_backend(vram_gb=VRAM_THRESHOLD_OLLAMA_70B - 0.1)
    assert backend == "airllm"
    # Pile sur le seuil → ollama
    backend, _ = recommend_backend(vram_gb=VRAM_THRESHOLD_OLLAMA_70B)
    assert backend == "ollama"
    # Zone 6-11 GB -> Ollama 14B
    backend, _ = recommend_backend(vram_gb=VRAM_THRESHOLD_AIRLLM - 0.1)
    assert backend == "ollama"
    # Sous 6 GB -> low latency 3B
    _, model = recommend_backend(vram_gb=5.9)
    assert "3b" in model.lower()


def test_recommend_backend_quality_mode_allows_14b_on_borderline_vram():
    backend, model = recommend_backend(vram_gb=5.0, ram_gb=32.0, priority="quality")
    assert backend == "ollama"
    assert "14b" in model.lower()


# ---------- detect_hardware ----------

def test_detect_hardware_returns_valid_object():
    info = detect_hardware()
    assert isinstance(info, HardwareInfo)
    assert info.os in ("windows", "linux", "darwin")
    assert info.cpu_cores >= 1
    assert info.recommended_local_backend in ("ollama", "airllm")
    assert info.recommended_local_model
    # Pas d'exception même si aucun GPU
    assert isinstance(info.vram_gb, float)
    assert isinstance(info.detection_warnings, list)


def test_detect_hardware_no_gpu_falls_back():
    """Si toutes les détections GPU échouent → vendor='none', vram=0."""
    with patch("agent.hardware_detect._try_nvidia", return_value=None), \
         patch("agent.hardware_detect._try_nvidia_smi", return_value=None), \
         patch("agent.hardware_detect._try_amd_rocm", return_value=None), \
         patch("agent.hardware_detect._try_windows_wmi", return_value=None):
        info = detect_hardware()
        assert info.has_gpu is False
        assert info.gpu_vendor == "none"
        assert info.vram_gb == 0.0
        assert info.recommended_local_backend == "ollama"


def test_detect_hardware_simulated_rtx_4090():
    """RTX 4090 (24 GB) → ollama 70B."""
    with patch("agent.hardware_detect._try_nvidia",
               return_value=("nvidia", "NVIDIA GeForce RTX 4090", 24.0)):
        info = detect_hardware()
        assert info.has_gpu is True
        assert info.gpu_vendor == "nvidia"
        assert info.vram_gb == 24.0
        assert info.recommended_local_backend == "ollama"


def test_detect_hardware_simulated_rtx_3060():
    """RTX 3060 (12 GB) → AirLLM."""
    with patch("agent.hardware_detect._try_nvidia",
               return_value=("nvidia", "NVIDIA GeForce RTX 3060", 12.0)):
        info = detect_hardware()
        assert info.has_gpu is True
        assert info.recommended_local_backend == "airllm"


# ---------- persistence ----------

def test_save_load_roundtrip():
    info = HardwareInfo(
        has_gpu=True, gpu_vendor="nvidia", gpu_name="RTX 4090",
        vram_gb=24.0, ram_gb=64.0,
        cpu_name="Intel i9", cpu_cores=16, os="windows",
        recommended_local_backend="ollama",
        recommended_local_model="huihui_ai/qwen2.5-72b-instruct-abliterated",
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "runtime.json"
        save_to_runtime(info, path)
        loaded = load_from_runtime(path)
        assert loaded is not None
        assert loaded.gpu_name == info.gpu_name
        assert loaded.vram_gb == info.vram_gb
        assert loaded.recommended_local_backend == info.recommended_local_backend


def test_load_from_missing_file_returns_none():
    assert load_from_runtime(Path("/nonexistent/path/runtime.json")) is None


def test_save_preserves_other_runtime_keys():
    """save_to_runtime ne doit pas écraser les autres clés du runtime.json."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "runtime.json"
        path.write_text(json.dumps({
            "first_launch_done": True,
            "last_boot": "2026-04-30",
        }), encoding="utf-8")

        info = HardwareInfo(
            has_gpu=False, gpu_vendor="none", gpu_name="none",
            vram_gb=0.0, ram_gb=32.0,
            cpu_name="Ryzen 7", cpu_cores=8, os="windows",
            recommended_local_backend="ollama",
            recommended_local_model="llama3.2-3b-instruct-abliterated",
        )
        save_to_runtime(info, path)

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["first_launch_done"] is True
        assert data["last_boot"] == "2026-04-30"
        assert "hardware" in data


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
