"""
Hardware detection — choisit le backend LLM local optimal.

Détecte CPU / RAM / GPU pour décider entre :
  - Ollama (modèle 70B sur GPU >= 24 GB)
  - AirLLM (modèle 70B sur GPU 12-23 GB via swap couche-par-couche)
  - Ollama small (modèle 14B sur CPU ou GPU < 12 GB)

Tolérant aux pannes : si une lib de détection GPU manque, fallback CPU-only.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


# ---------- thresholds ----------

VRAM_THRESHOLD_OLLAMA_70B = 24.0   # GB — Ollama natif fluide pour 70B
VRAM_THRESHOLD_AIRLLM     = 12.0   # GB — AirLLM utile pour 70B
VRAM_THRESHOLD_OLLAMA_14B = 6.0    # GB — Ollama 14B GPU-accelerated

DEFAULT_MODEL_70B  = "huihui_ai/qwen2.5-72b-instruct-abliterated"
DEFAULT_MODEL_AIRLLM = "huihui-ai/Qwen2.5-72B-Instruct-abliterated"
DEFAULT_MODEL_14B  = "huihui_ai/qwen2.5-abliterate:14b"


# ---------- dataclass ----------

@dataclass
class HardwareInfo:
    has_gpu:                   bool
    gpu_vendor:                str       # "nvidia" | "amd" | "intel" | "apple" | "none"
    gpu_name:                  str
    vram_gb:                   float
    ram_gb:                    float
    cpu_name:                  str
    cpu_cores:                 int
    os:                        str       # "windows" | "linux" | "darwin"
    recommended_local_backend: str       # "ollama" | "airllm" | "ollama_small"
    recommended_local_model:   str
    detection_warnings:        list[str] = field(default_factory=list)


# ---------- détection ----------

def detect_hardware() -> HardwareInfo:
    """Détection complète. Toujours retourne un HardwareInfo (jamais raise)."""
    warnings: list[str] = []
    os_name = platform.system().lower()
    cpu_name = platform.processor() or platform.machine()
    cpu_cores = _cpu_count()
    ram_gb = _ram_gb(warnings)

    gpu_vendor, gpu_name, vram_gb = _detect_gpu(warnings)

    backend, model = recommend_backend(vram_gb)

    return HardwareInfo(
        has_gpu=gpu_vendor != "none",
        gpu_vendor=gpu_vendor,
        gpu_name=gpu_name,
        vram_gb=vram_gb,
        ram_gb=ram_gb,
        cpu_name=cpu_name,
        cpu_cores=cpu_cores,
        os=os_name,
        recommended_local_backend=backend,
        recommended_local_model=model,
        detection_warnings=warnings,
    )


def recommend_backend(vram_gb: float) -> tuple[str, str]:
    """(backend, model) selon VRAM disponible."""
    if vram_gb >= VRAM_THRESHOLD_OLLAMA_70B:
        return "ollama", DEFAULT_MODEL_70B
    if vram_gb >= VRAM_THRESHOLD_AIRLLM:
        return "airllm", DEFAULT_MODEL_AIRLLM
    return "ollama_small", DEFAULT_MODEL_14B


# ---------- helpers internes ----------

def _cpu_count() -> int:
    try:
        import os
        return os.cpu_count() or 1
    except Exception:
        return 1


def _ram_gb(warnings: list[str]) -> float:
    try:
        import psutil
        return round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception as e:
        warnings.append(f"RAM detect failed: {e}")
        return 0.0


def _detect_gpu(warnings: list[str]) -> tuple[str, str, float]:
    """Retourne (vendor, name, vram_gb). vendor='none' si pas de GPU dédié."""
    # 1) NVIDIA via pynvml
    nv = _try_nvidia()
    if nv is not None:
        return nv

    # 2) NVIDIA via nvidia-smi (si pynvml absent)
    nv = _try_nvidia_smi()
    if nv is not None:
        return nv

    # 3) AMD ROCm via rocm-smi
    amd = _try_amd_rocm()
    if amd is not None:
        return amd

    # 4) Apple Silicon (Metal)
    if platform.system() == "Darwin" and platform.machine() in ("arm64", "aarch64"):
        return _detect_apple_silicon()

    # 5) Windows : WMI pour iGPU/dGPU au moins par nom
    if platform.system() == "Windows":
        wmi = _try_windows_wmi(warnings)
        if wmi is not None:
            return wmi

    return "none", "none", 0.0


def _try_nvidia() -> Optional[tuple[str, str, float]]:
    try:
        import pynvml
        pynvml.nvmlInit()
        try:
            count = pynvml.nvmlDeviceGetCount()
            if count == 0:
                return None
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode()
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            vram_gb = round(mem.total / (1024 ** 3), 1)
            return "nvidia", name, vram_gb
        finally:
            pynvml.nvmlShutdown()
    except Exception:
        return None


def _try_nvidia_smi() -> Optional[tuple[str, str, float]]:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0:
            return None
        line = out.stdout.strip().splitlines()[0]
        name, mem_mib = [s.strip() for s in line.split(",")]
        vram_gb = round(float(mem_mib) / 1024, 1)
        return "nvidia", name, vram_gb
    except Exception:
        return None


def _try_amd_rocm() -> Optional[tuple[str, str, float]]:
    if not shutil.which("rocm-smi"):
        return None
    try:
        out = subprocess.run(
            ["rocm-smi", "--showproductname", "--showmeminfo", "vram", "--json"],
            capture_output=True, text=True, timeout=5,
        )
        data = json.loads(out.stdout)
        first = next(iter(data.values()), {})
        name = first.get("Card series", "AMD GPU")
        vram_str = first.get("VRAM Total Memory (B)", "0")
        vram_gb = round(int(vram_str) / (1024 ** 3), 1)
        return "amd", name, vram_gb
    except Exception:
        return None


def _try_windows_wmi(warnings: list[str]) -> Optional[tuple[str, str, float]]:
    """Fallback Windows : PowerShell Get-CimInstance Win32_VideoController."""
    try:
        cmd = (
            "powershell -NoProfile -Command "
            "\"Get-CimInstance Win32_VideoController | "
            "Select-Object Name,AdapterRAM | ConvertTo-Json\""
        )
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10, shell=True)
        if out.returncode != 0 or not out.stdout.strip():
            return None
        data = json.loads(out.stdout)
        if isinstance(data, dict):
            data = [data]
        # Choisis l'adaptateur avec le plus de RAM (= dGPU si présent)
        best = max(data, key=lambda d: int(d.get("AdapterRAM") or 0))
        name = best.get("Name", "Unknown GPU")
        ram_bytes = int(best.get("AdapterRAM") or 0)
        vram_gb = round(ram_bytes / (1024 ** 3), 1)
        # AdapterRAM est buggé sur Windows (cap 4 GB sur certains GPUs).
        # On warn si nom suggère un GPU > 4 GB mais ram_bytes ≈ 4 GB.
        if vram_gb >= 3.9 and vram_gb <= 4.1:
            warnings.append(
                f"Windows WMI peut sous-estimer la VRAM (cap 4 GB). "
                f"GPU détecté: {name}. Installe pynvml pour mesure exacte."
            )
        vendor = "nvidia" if "nvidia" in name.lower() or "geforce" in name.lower() or "rtx" in name.lower() \
            else "amd" if "amd" in name.lower() or "radeon" in name.lower() \
            else "intel" if "intel" in name.lower() \
            else "unknown"
        return vendor, name, vram_gb
    except Exception as e:
        warnings.append(f"WMI GPU detect failed: {e}")
        return None


def _detect_apple_silicon() -> tuple[str, str, float]:
    """Apple Silicon : RAM unifiée = "VRAM" usable. Approximation 75% de la RAM."""
    try:
        import psutil
        ram = psutil.virtual_memory().total / (1024 ** 3)
        return "apple", "Apple Silicon (unified memory)", round(ram * 0.75, 1)
    except Exception:
        return "apple", "Apple Silicon", 0.0


# ---------- persistence ----------

def save_to_runtime(info: HardwareInfo, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["hardware"] = asdict(info)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_from_runtime(path: Path) -> Optional[HardwareInfo]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        hw = data.get("hardware")
        if not hw:
            return None
        return HardwareInfo(**hw)
    except Exception:
        return None


# ---------- CLI ----------

if __name__ == "__main__":
    info = detect_hardware()
    print("🔍 Hardware Detection")
    print(f"  OS:          {info.os}")
    print(f"  CPU:         {info.cpu_name} ({info.cpu_cores} cores)")
    print(f"  RAM:         {info.ram_gb} GB")
    print(f"  GPU:         {info.gpu_name} ({info.gpu_vendor})")
    print(f"  VRAM:        {info.vram_gb} GB")
    print(f"  → Backend:   {info.recommended_local_backend}")
    print(f"  → Modèle:    {info.recommended_local_model}")
    if info.detection_warnings:
        print("\n⚠️  Warnings:")
        for w in info.detection_warnings:
            print(f"  - {w}")
