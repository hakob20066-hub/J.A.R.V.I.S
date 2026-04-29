"""
Awareness pipeline — thread continu :
  - capture écran (mss) toutes N secondes
  - OCR léger (optionnel) pour extraire texte
  - détection "struggle" simple (même fenêtre/texte > X cycles → stagnation)
  - inject contexte dans un buffer partagé (récupérable par le main agent)

Fallback silencieux si mss/pytesseract indispo.
"""

from __future__ import annotations

import hashlib
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable, Optional


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()


class AwarenessPipeline:
    """
    Thread :
      every interval_s: grab screen → hash → optional OCR → buffer.
      Si même hash N fois consécutives → flag 'struggle' = True.
    """

    def __init__(
        self,
        interval_s: float = 10.0,
        ocr: bool = False,
        on_struggle: Optional[Callable[[str], None]] = None,
        struggle_threshold: int = 3,
        history: int = 10,
    ):
        self.interval_s        = interval_s
        self.ocr               = ocr
        self.on_struggle       = on_struggle
        self.struggle_threshold = struggle_threshold
        self.history_buf: deque = deque(maxlen=history)

        self._stop   = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._same_count = 0
        self._last_hash  = ""
        self._last_text  = ""
        self._context_lock = threading.Lock()

        self._available = self._check_deps()

    def _check_deps(self) -> bool:
        try:
            import mss  # noqa: F401
            return True
        except Exception as e:
            print(f"[Awareness] ⚠️ disabled ({e})")
            return False

    # ---------- public ----------

    def start(self) -> None:
        if not self._available or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[Awareness] 👁️ pipeline started (interval={self.interval_s}s)")

    def stop(self) -> None:
        self._stop.set()

    def get_context(self, max_chars: int = 500) -> str:
        """Texte résumé utilisable comme context injection pour le LLM."""
        with self._context_lock:
            if not self.history_buf:
                return ""
            last = list(self.history_buf)[-3:]
            joined = " | ".join(h.get("text", "")[:120] for h in last if h.get("text"))
            if self._same_count >= self.struggle_threshold:
                joined = "⚠️ user appears stuck on same screen. " + joined
            return joined[:max_chars]

    # ---------- loop ----------

    def _loop(self) -> None:
        try:
            import mss
        except Exception as e:
            print(f"[Awareness] ⚠️ mss failed: {e}")
            return

        try:
            import pytesseract  # type: ignore
            ocr_ok = True
        except Exception:
            ocr_ok = False

        sct = mss.mss()
        try:
            while not self._stop.is_set():
                try:
                    monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                    img     = sct.grab(monitor)
                    raw     = bytes(img.rgb)
                    h       = hashlib.md5(raw).hexdigest()

                    text = ""
                    if self.ocr and ocr_ok:
                        try:
                            from PIL import Image
                            pil = Image.frombytes("RGB", img.size, raw)
                            # Downscale pour perfs
                            pil.thumbnail((1280, 720))
                            text = pytesseract.image_to_string(pil)[:500]
                        except Exception as e:
                            print(f"[Awareness] ⚠️ OCR: {e}")

                    with self._context_lock:
                        if h == self._last_hash:
                            self._same_count += 1
                        else:
                            self._same_count = 0
                        self._last_hash = h
                        self._last_text = text
                        self.history_buf.append({
                            "ts": time.time(), "hash": h, "text": text,
                        })

                        if (
                            self._same_count == self.struggle_threshold
                            and self.on_struggle
                        ):
                            try:
                                self.on_struggle(text or "same screen for a while")
                            except Exception as e:
                                print(f"[Awareness] ⚠️ struggle cb: {e}")

                except Exception as e:
                    print(f"[Awareness] ⚠️ capture error: {e}")

                self._stop.wait(self.interval_s)
        finally:
            try:
                sct.close()
            except Exception:
                pass


_AW_SINGLETON: Optional[AwarenessPipeline] = None


def start_awareness(**kw) -> AwarenessPipeline:
    global _AW_SINGLETON
    if _AW_SINGLETON is None:
        _AW_SINGLETON = AwarenessPipeline(**kw)
    _AW_SINGLETON.start()
    return _AW_SINGLETON


def get_awareness_context(max_chars: int = 500) -> str:
    if _AW_SINGLETON is None:
        return ""
    return _AW_SINGLETON.get_context(max_chars=max_chars)
