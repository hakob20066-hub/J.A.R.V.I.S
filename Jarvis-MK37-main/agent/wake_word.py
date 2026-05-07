"""
Wake Word detector — 3 backends (priorité décroissante) :
  1. Porcupine (picovoice) — keyword "jarvis" built-in. Requires access key.
  2. Vosk — STT offline, match "jarvis" dans le texte. 100% gratuit, pas de compte.
  3. openwakeword — modèle ONNX, par défaut "hey_jarvis" (custom possible).

Config :
  config/api_keys.json → "picovoice_access_key": "..." (optionnel)
  models/vosk/  → décompresser modèle Vosk ici (vosk-model-small-fr-0.22 ou en-us)

Fallback silencieux si rien dispo → thread no-op.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR     = _base_dir()
API_CONFIG   = BASE_DIR / "config" / "api_keys.json"
MODELS_DIR   = BASE_DIR / "models" / "wakewords"

DEFAULT_KEYWORD = "jarvis"


def _load_picovoice_key() -> str:
    try:
        cfg = json.loads(API_CONFIG.read_text(encoding="utf-8"))
        return cfg.get("picovoice_access_key", "")
    except Exception:
        return ""


class WakeWordDetector:
    def __init__(
        self,
        on_detect: Callable[[str], None],
        keyword: str = DEFAULT_KEYWORD,
        threshold: float = 0.5,
        cooldown_s: float = 2.0,
    ):
        self.on_detect  = on_detect
        self.keyword    = keyword
        self.threshold  = threshold
        self.cooldown_s = cooldown_s
        self._stop      = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._backend   = self._pick_backend()

    def _pick_backend(self) -> str:
        try:
            import pvporcupine  # noqa: F401
            import pvrecorder   # noqa: F401
            if _load_picovoice_key():
                return "porcupine"
        except Exception:
            pass
        try:
            import vosk           # noqa: F401
            import sounddevice    # noqa: F401
            if (BASE_DIR / "models" / "vosk").exists():
                return "vosk"
        except Exception:
            pass
        try:
            import openwakeword  # noqa: F401
            import sounddevice   # noqa: F401
            import numpy         # noqa: F401
            return "openwakeword"
        except Exception:
            pass
        print("[WakeWord] ⚠️ no backend available (porcupine / vosk / openwakeword)")
        return "none"

    # ---------- public ----------

    def start(self) -> None:
        if self._backend == "none":
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        targets = {
            "porcupine":    self._loop_porcupine,
            "vosk":         self._loop_vosk,
            "openwakeword": self._loop_oww,
        }
        target = targets.get(self._backend)
        if not target:
            return
        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()
        print(f"[WakeWord] 🎙️ listening for '{self.keyword}' (backend={self._backend})")

    def stop(self) -> None:
        self._stop.set()

    # ---------- porcupine loop ----------

    def _loop_porcupine(self) -> None:
        try:
            import pvporcupine
            from pvrecorder import PvRecorder
        except Exception as e:
            print(f"[WakeWord] ⚠️ porcupine import failed: {e}")
            return

        access_key = _load_picovoice_key()
        try:
            porcupine = pvporcupine.create(
                access_key=access_key,
                keywords=[self.keyword],
            )
        except Exception as e:
            print(f"[WakeWord] ⚠️ porcupine init failed: {e}")
            return

        recorder = PvRecorder(frame_length=porcupine.frame_length, device_index=-1)
        recorder.start()
        last_detect = 0.0
        try:
            while not self._stop.is_set():
                pcm = recorder.read()
                idx = porcupine.process(pcm)
                if idx >= 0:
                    now = time.time()
                    if now - last_detect < self.cooldown_s:
                        continue
                    last_detect = now
                    print(f"[WakeWord] ✅ '{self.keyword}' detected")
                    try:
                        self.on_detect(self.keyword)
                    except Exception as e:
                        print(f"[WakeWord] ⚠️ callback error: {e}")
        except Exception as e:
            print(f"[WakeWord] ⚠️ porcupine loop error: {e}")
        finally:
            try:
                recorder.stop(); recorder.delete(); porcupine.delete()
            except Exception:
                pass

    # ---------- vosk loop (STT offline, match keyword in text) ----------

    def _loop_vosk(self) -> None:
        try:
            import vosk
            import sounddevice as sd
            import queue as _q
        except Exception as e:
            print(f"[WakeWord] ⚠️ vosk import failed: {e}")
            return

        model_dir = BASE_DIR / "models" / "vosk"
        # Pick first subdir as model
        sub = next((p for p in model_dir.iterdir() if p.is_dir()), None) if model_dir.exists() else None
        if not sub:
            print(f"[WakeWord] ⚠️ no vosk model found in {model_dir}")
            return

        try:
            vosk.SetLogLevel(-1)
            model = vosk.Model(str(sub))
            rec   = vosk.KaldiRecognizer(model, 16000)
        except Exception as e:
            print(f"[WakeWord] ⚠️ vosk model load failed: {e}")
            return

        q: "_q.Queue[bytes]" = _q.Queue()

        def _cb(indata, frames, t, status):
            q.put(bytes(indata))

        last_detect = 0.0
        keyword = self.keyword.lower()
        try:
            with sd.RawInputStream(
                samplerate=16000, blocksize=8000, dtype="int16",
                channels=1, callback=_cb,
            ):
                while not self._stop.is_set():
                    try:
                        data = q.get(timeout=0.5)
                    except _q.Empty:
                        continue
                    if rec.AcceptWaveform(data):
                        import json as _j
                        txt = _j.loads(rec.Result()).get("text", "").lower()
                    else:
                        import json as _j
                        txt = _j.loads(rec.PartialResult()).get("partial", "").lower()
                    if keyword in txt:
                        now = time.time()
                        if now - last_detect < self.cooldown_s:
                            continue
                        last_detect = now
                        print(f"[WakeWord] ✅ '{keyword}' (vosk: {txt[:60]})")
                        try:
                            self.on_detect(keyword)
                        except Exception as e:
                            print(f"[WakeWord] ⚠️ callback error: {e}")
                        rec.Reset()
        except Exception as e:
            print(f"[WakeWord] ⚠️ vosk stream error: {e}")

    # ---------- openwakeword loop (fallback) ----------

    def _loop_oww(self) -> None:
        try:
            from openwakeword.model import Model
            import sounddevice as sd
            import numpy as np
        except Exception as e:
            print(f"[WakeWord] ⚠️ oww import failed: {e}")
            return

        SAMPLE_RATE = 16000
        CHUNK       = 1280
        try:
            custom = MODELS_DIR / "jarvis.onnx"
            if custom.exists():
                model = Model(wakeword_models=[str(custom)])
            else:
                # Charge uniquement "hey_jarvis" → pas de faux positifs sur
                # alexa/computer/etc. Télécharge les modèles si absents.
                try:
                    model = Model(wakeword_models=["hey_jarvis"])
                except Exception:
                    import openwakeword.utils as _oww_utils
                    _oww_utils.download_models()
                    model = Model(wakeword_models=["hey_jarvis"])
        except Exception as e:
            print(f"[WakeWord] ⚠️ oww model failed: {e}")
            return

        last_detect = 0.0
        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=CHUNK,
            ) as stream:
                while not self._stop.is_set():
                    data, _ = stream.read(CHUNK)
                    arr = np.frombuffer(data.tobytes(), dtype=np.int16)
                    preds = model.predict(arr)
                    for kw, score in preds.items():
                        if score >= self.threshold:
                            now = time.time()
                            if now - last_detect < self.cooldown_s:
                                continue
                            last_detect = now
                            print(f"[WakeWord] ✅ '{kw}' ({score:.2f})")
                            try:
                                self.on_detect(kw)
                            except Exception as e:
                                print(f"[WakeWord] ⚠️ callback error: {e}")
        except Exception as e:
            print(f"[WakeWord] ⚠️ oww stream error: {e}")


_WW_SINGLETON: Optional[WakeWordDetector] = None


def start_wake_word(on_detect: Callable[[str], None], **kw) -> WakeWordDetector:
    global _WW_SINGLETON
    if _WW_SINGLETON is None:
        _WW_SINGLETON = WakeWordDetector(on_detect=on_detect, **kw)
    _WW_SINGLETON.start()
    return _WW_SINGLETON
