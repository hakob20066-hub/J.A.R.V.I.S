"""
Clap Detector — détecte un double clap des mains et déclenche un callback.

Principe :
  - Reçoit les samples audio int16 mono (feed)
  - Chaque chunk : peak absolu normalisé [0,1]
  - Clap = peak > THRESHOLD précédé d'un chunk silencieux (< SILENCE)
  - Double clap = 2 claps espacés entre MIN_GAP_MS et MAX_GAP_MS
  - Cooldown après déclenchement pour éviter rafale

Usage :
    det = ClapDetector(on_double_clap=my_callback)
    # dans le sounddevice callback :
    det.feed(indata)
"""

from __future__ import annotations

import os
import time
from collections import deque
from typing import Callable, Optional

import numpy as np


class ClapDetector:
    # Params tunables (env override: JARVIS_CLAP_THRESHOLD, JARVIS_CLAP_DEBUG=1)
    THRESHOLD   = 0.18   # peak > 18% pour compter comme clap candidat
    SILENCE     = 0.08   # chunk précédent doit être sous ce niveau
    MIN_GAP_MS  = 150    # intervalle min entre 2 claps
    MAX_GAP_MS  = 1200   # intervalle max
    COOLDOWN_MS = 3000   # après déclenchement, ignore N ms

    def __init__(
        self,
        on_double_clap: Callable[[], None],
        threshold: Optional[float] = None,
    ):
        self.on_double_clap = on_double_clap
        env_th = os.environ.get("JARVIS_CLAP_THRESHOLD")
        if threshold is not None:
            self.THRESHOLD = threshold
        elif env_th:
            try:
                self.THRESHOLD = float(env_th)
            except Exception:
                pass
        self._debug = os.environ.get("JARVIS_CLAP_DEBUG", "") == "1"
        self._last_peak = 0.0            # peak du chunk précédent
        self._max_seen  = 0.0
        self._clap_times: deque[float] = deque(maxlen=4)
        self._last_trigger = 0.0
        self._last_debug_t = 0.0
        self._enabled = True
        print(f"[ClapDetector] threshold={self.THRESHOLD:.2f} silence={self.SILENCE:.2f} debug={self._debug}")

    def enable(self, val: bool = True):
        self._enabled = val

    def feed(self, indata) -> None:
        if not self._enabled:
            return
        try:
            # indata: numpy int16 shape (frames, channels) ou bytes
            if isinstance(indata, (bytes, bytearray)):
                arr = np.frombuffer(indata, dtype=np.int16)
            else:
                arr = np.asarray(indata).reshape(-1)
            if arr.size == 0:
                return
            peak = float(np.max(np.abs(arr))) / 32768.0
            now  = time.time()

            if peak > self._max_seen:
                self._max_seen = peak

            # Debug : print max observé toutes les 2s
            if self._debug and (now - self._last_debug_t) > 2.0:
                self._last_debug_t = now
                print(f"[ClapDetector] max_last_2s={self._max_seen:.2f} (threshold={self.THRESHOLD:.2f})")
                self._max_seen = 0.0

            # Clap détecté : peak fort, précédé de quasi-silence
            if peak >= self.THRESHOLD and self._last_peak < self.SILENCE:
                # cooldown après trigger
                if (now - self._last_trigger) * 1000 < self.COOLDOWN_MS:
                    self._last_peak = peak
                    return
                if self._debug:
                    print(f"[ClapDetector] 👏 peak={peak:.2f} prev={self._last_peak:.2f}")
                self._clap_times.append(now)
                # cherche un double clap dans la fenêtre
                if len(self._clap_times) >= 2:
                    gap_ms = (self._clap_times[-1] - self._clap_times[-2]) * 1000
                    if self._debug:
                        print(f"[ClapDetector] gap={gap_ms:.0f}ms (win {self.MIN_GAP_MS}-{self.MAX_GAP_MS})")
                    if self.MIN_GAP_MS <= gap_ms <= self.MAX_GAP_MS:
                        self._last_trigger = now
                        self._clap_times.clear()
                        try:
                            self.on_double_clap()
                        except Exception as e:
                            print(f"[ClapDetector] callback error: {e}")
            self._last_peak = peak
        except Exception:
            pass
