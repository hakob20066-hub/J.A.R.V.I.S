"""
KaliRunner — détection backend + exec sécurisée.

Voir [[14-Phases/phase7.6-kali-runner]].

Backends prioritaires :
  1. WSL Kali       (`wsl -d kali-linux -- ...`)
  2. WSL Ubuntu     (autre distro avec apt + tools)
  3. Native Linux   (`which sherlock`)
  4. Docker         (`docker run kalilinux/kali-rolling`)
  5. None           → fallback Python uniquement
"""
from __future__ import annotations

import asyncio
import json
import platform
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class KaliResult:
    success:    bool
    stdout:     str
    stderr:     str
    returncode: int
    elapsed_ms: int
    parsed:     Any = None
    error:      Optional[str] = None


KALI_DISTROS = ["kali-linux", "kali-rolling", "Kali-Linux", "Kali"]
UBUNTU_DISTROS = ["Ubuntu", "Ubuntu-22.04", "Ubuntu-20.04", "Debian"]


class KaliRunner:
    """Détecte au boot puis exec via le backend choisi."""

    def __init__(self):
        self.backend: str = "none"          # 'wsl_kali' | 'wsl_ubuntu' | 'native' | 'docker' | 'none'
        self.distro_name: Optional[str] = None
        self._tool_cache: dict[str, bool] = {}
        self.detect()

    # ---------- detection ----------

    def detect(self) -> str:
        if platform.system() == "Linux":
            # Native Linux ?
            if shutil.which("sherlock") or shutil.which("apt"):
                self.backend = "native"
                self.distro_name = "linux"
                return self.backend

        if platform.system() == "Windows":
            # WSL dispo ?
            if shutil.which("wsl"):
                distros = self._list_wsl_distros()
                # Prefer Kali
                for k in KALI_DISTROS:
                    if k in distros:
                        self.backend = "wsl_kali"
                        self.distro_name = k
                        return self.backend
                for u in UBUNTU_DISTROS:
                    if u in distros:
                        self.backend = "wsl_ubuntu"
                        self.distro_name = u
                        return self.backend

        # Docker fallback
        if shutil.which("docker"):
            try:
                r = subprocess.run(["docker", "image", "ls", "kalilinux/kali-rolling", "--format", "{{.Repository}}"],
                                   capture_output=True, text=True, timeout=5)
                if "kali" in r.stdout.lower():
                    self.backend = "docker"
                    self.distro_name = "kalilinux/kali-rolling"
                    return self.backend
            except Exception:
                pass

        self.backend = "none"
        return self.backend

    @staticmethod
    def _list_wsl_distros() -> list[str]:
        try:
            r = subprocess.run(["wsl", "--list", "--quiet"], capture_output=True, text=True, timeout=5)
            # WSL output is UTF-16 sometimes, retry with bytes
            raw = r.stdout
            if not raw or "\x00" in raw:
                r = subprocess.run(["wsl", "--list", "--quiet"], capture_output=True, timeout=5)
                raw = r.stdout.decode("utf-16-le", errors="ignore")
            return [line.strip() for line in raw.splitlines() if line.strip()]
        except Exception:
            return []

    # ---------- tool availability ----------

    def is_tool_available(self, tool_name: str) -> bool:
        if tool_name in self._tool_cache:
            return self._tool_cache[tool_name]
        if self.backend == "none":
            self._tool_cache[tool_name] = False
            return False

        try:
            cmd = self._wrap(["which", tool_name])
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            ok = r.returncode == 0 and bool(r.stdout.strip())
        except Exception:
            ok = False
        self._tool_cache[tool_name] = ok
        return ok

    def list_tools(self, names: list[str]) -> dict[str, bool]:
        return {n: self.is_tool_available(n) for n in names}

    # ---------- exec ----------

    def _wrap(self, cmd: list[str]) -> list[str]:
        """Préfixe la commande selon le backend."""
        if self.backend == "wsl_kali" or self.backend == "wsl_ubuntu":
            return ["wsl", "-d", self.distro_name, "--"] + cmd
        if self.backend == "docker":
            return ["docker", "run", "--rm", self.distro_name] + cmd
        return cmd  # native

    async def run(
        self,
        cmd: list[str],
        timeout: int = 60,
        json_output: bool = False,
        stdin: Optional[str] = None,
    ) -> KaliResult:
        if self.backend == "none":
            return KaliResult(False, "", "", -1, 0, error="No Kali backend available")

        wrapped = self._wrap(cmd)
        t0 = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_exec(
                *wrapped,
                stdin=asyncio.subprocess.PIPE if stdin else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdin_bytes = stdin.encode("utf-8") if stdin else None
            try:
                out, err = await asyncio.wait_for(
                    proc.communicate(input=stdin_bytes), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return KaliResult(False, "", "timeout", -1,
                                  int((time.perf_counter() - t0) * 1000),
                                  error=f"timeout after {timeout}s")
            stdout = out.decode("utf-8", errors="replace")
            stderr = err.decode("utf-8", errors="replace")
            elapsed = int((time.perf_counter() - t0) * 1000)
            success = proc.returncode == 0

            parsed = None
            if json_output and stdout.strip():
                try:
                    parsed = json.loads(stdout)
                except json.JSONDecodeError:
                    pass

            return KaliResult(success, stdout, stderr, proc.returncode, elapsed, parsed)
        except FileNotFoundError as e:
            return KaliResult(False, "", "", -1, 0, error=f"backend command not found: {e}")
        except Exception as e:
            return KaliResult(False, "", "", -1, 0, error=str(e))

    # ---------- install ----------

    async def install_tool(self, package: str, on_progress=None) -> bool:
        """
        apt install (avec confirmation user déjà obtenue côté wizard).
        Renvoie False si backend=none.
        """
        if self.backend == "none":
            return False
        cmd = ["sudo", "apt", "install", "-y", package]
        result = await self.run(cmd, timeout=300)
        return result.success

    # ---------- snapshot ----------

    def status(self) -> dict:
        return {
            "backend":     self.backend,
            "distro":      self.distro_name,
            "tool_cache":  dict(self._tool_cache),
            "available":   self.backend != "none",
        }


_RUNNER_SINGLETON: Optional[KaliRunner] = None


def get_runner() -> KaliRunner:
    global _RUNNER_SINGLETON
    if _RUNNER_SINGLETON is None:
        _RUNNER_SINGLETON = KaliRunner()
    return _RUNNER_SINGLETON


def reset_runner() -> None:
    global _RUNNER_SINGLETON
    _RUNNER_SINGLETON = None
