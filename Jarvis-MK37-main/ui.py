"""
J.A.R.V.I.S â€” UI (MARK XXXVII)

FenÃªtre desktop native via pywebview rendant `ui.html`.
Bridge JS<->Python minimal (pas de polling, pas de timer Python).
API publique conservÃ©e pour main.py :
    - JarvisUI(face_path)
    - .root.mainloop()
    - .set_state(state)
    - .write_log(text)
    - .wait_for_api_key()
    - .muted (attribut)
    - .on_text_command (callback)
    - .start_speaking() / .stop_speaking()
"""

import os
import sys
import json
import time
import platform
import threading
from pathlib import Path
from queue import Queue, Empty

import webview

from config.secure_api_keys import is_api_config_encrypted, load_api_config, save_api_config

SYSTEM_NAME = "J.A.R.V.I.S"
MODEL_BADGE = "MARK XXXVII"

_STATE_MAP = {
    "SPEAKING":    "responding",
    "LISTENING":   "listening",
    "THINKING":    "processing",
    "PROCESSING":  "processing",
    "MUTED":       "idle",
    "INITIALISING":"idle",
    "ONLINE":      "idle",
    "ERROR":       "error",
}


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR   = get_base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"
HTML_FILE  = BASE_DIR / "ui.html"


def _js_str(s: str) -> str:
    """Safe JS string literal (no template injection)."""
    return json.dumps(s if s is not None else "")


class _Api:
    """JS -> Python bridge. ExposÃ© Ã  pywebview via js_api."""
    def __init__(self, ui: "JarvisUI"):
        self._ui = ui

    def send_text(self, text: str):
        self._ui._handle_user_text(text or "")
        return True

    def toggle_mute(self):
        self._ui._toggle_mute()
        return self._ui.muted

    def get_initial_state(self):
        return {
            "muted":        self._ui.muted,
            "system_name":  SYSTEM_NAME,
            "model_badge":  MODEL_BADGE,
        }

    # Phase 7.5: Safety Controls API
    def get_demo_mode(self):
        """Retourne l'état du mode demo depuis JarvisLive."""
        if hasattr(self._ui, '_jarvis_instance') and self._ui._jarvis_instance:
            return self._ui._jarvis_instance.get_demo_mode()
        return False

    def set_demo_mode(self, enabled: bool):
        """Active/désactive le mode demo."""
        if hasattr(self._ui, '_jarvis_instance') and self._ui._jarvis_instance:
            self._ui._jarvis_instance.set_demo_mode(enabled)
            return True
        return False

    def get_emergency_status(self):
        """Retourne le statut du système d'urgence."""
        if hasattr(self._ui, '_jarvis_instance') and self._ui._jarvis_instance:
            return self._ui._jarvis_instance.get_emergency_status()
        return {}

    def trigger_emergency_stop(self):
        """Déclenche l'arrêt d'urgence."""
        if hasattr(self._ui, '_jarvis_instance') and self._ui._jarvis_instance:
            self._ui._jarvis_instance.trigger_emergency_stop()
            return True
        return False

    def get_last_action(self):
        """Retourne la dernière action pour rollback."""
        if hasattr(self._ui, '_jarvis_instance') and self._ui._jarvis_instance:
            return self._ui._jarvis_instance.get_last_action()
        return None

    def rollback_last_action(self):
        """Tente d'annuler la dernière action."""
        if hasattr(self._ui, '_jarvis_instance') and self._ui._jarvis_instance:
            return self._ui._jarvis_instance.rollback_last_action()
        return "Jarvis instance not available"

    # Phase 7.6: OSINT API
    def osint_cancel(self):
        """Annule la cascade OSINT en cours."""
        try:
            from agent.osint import get_engine
            get_engine().cancel()
            self._ui.osint_panel_cancel()
            return True
        except Exception as e:
            print(f"[UI] osint_cancel: {e}")
            return False

    def osint_get_state(self):
        """Snapshot UI state (engine + scheduler + last report)."""
        try:
            from agent.osint import get_engine, get_runner
            return {
                "kali_backend": get_runner().backend,
                "kali_distro":  get_runner().distro_name,
                "scheduler":    get_engine().scheduler.status(),
            }
        except Exception:
            return {"kali_backend": "none"}

    def osint_save_dropped_image(self, filename: str, b64: str) -> str:
        """Sauve image droppée dans le panel."""
        import base64, time as _t
        drop_dir = BASE_DIR / "memory" / "osint_drops"
        drop_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c for c in filename if c.isalnum() or c in "._-")
        path = drop_dir / f"{int(_t.time())}_{safe_name}"
        path.write_bytes(base64.b64decode(b64))
        return str(path)

    def osint_lookup_image(self, path: str) -> bool:
        """Déclenche cascade OSINT type=image après drop."""
        if hasattr(self._ui, '_jarvis_instance') and self._ui._jarvis_instance:
            try:
                self._ui._jarvis_instance.trigger_osint_lookup(path, type_hint="image")
                return True
            except Exception:
                pass
        # Fallback : lance direct sans Jarvis
        try:
            from agent.osint import get_engine
            import threading
            t = threading.Thread(
                target=lambda: get_engine().lookup(path, mode="self_audit", depth=2),
                daemon=True,
            )
            t.start()
            return True
        except Exception as e:
            print(f"[UI] osint_lookup_image: {e}")
            return False


class _RootShim:
    """Compat avec main.py qui appelle ui.root.mainloop()."""
    def __init__(self, ui: "JarvisUI"):
        self._ui = ui
    def mainloop(self):
        self._ui._start_webview()


class JarvisUI:
    def __init__(self, face_path=None, size=None):
        # face_path ignorÃ©: nouvelle UI 100% procÃ©durale canvas
        self.muted            = False
        self.on_text_command  = None
        self._jarvis_state    = "INITIALISING"
        self._window          = None
        self._api             = _Api(self)
        self._js_queue        = Queue()
        self._window_ready    = False

        self._api_key_ready = self._api_keys_exist()
        if not self._api_key_ready:
            self._run_setup_dialog()

        self.root = _RootShim(self)

    # â”€â”€ pywebview lifecycle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _start_webview(self):
        if not HTML_FILE.exists():
            raise FileNotFoundError(f"UI HTML missing: {HTML_FILE}")
        html = HTML_FILE.read_text(encoding="utf-8")

        self._window = webview.create_window(
            f"{SYSTEM_NAME} â€” {MODEL_BADGE}",
            html=html,
            js_api=self._api,
            width=1280,
            height=820,
            min_size=(960, 640),
            resizable=True,
            background_color="#0a0e14",
        )
        self._window.events.loaded += self._on_loaded

        gui = os.environ.get("JARVIS_WEBVIEW_GUI")
        if not gui:
            try:
                import clr  # noqa: F401
                gui = None
            except ImportError:
                gui = "qt"
                print("[UI] pythonnet absent -> backend Qt")

        webview.start(debug=False, gui=gui)

    def _on_loaded(self):
        self._window_ready = True
        # Flush JS diffÃ©rÃ©
        while True:
            try:
                js = self._js_queue.get_nowait()
            except Empty:
                break
            self._safe_eval(js)

    def _safe_eval(self, js: str):
        try:
            self._window.evaluate_js(js)
        except Exception:
            pass

    def _run_js(self, js: str):
        if self._window_ready and self._window is not None:
            self._safe_eval(js)
        else:
            self._js_queue.put(js)

    # â”€â”€ public API (compat main.py) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def set_state(self, state: str):
        self._jarvis_state = state
        js_state = _STATE_MAP.get(state, "idle")
        self._run_js(f"window.jarvisSetState && window.jarvisSetState({_js_str(js_state)});")

    def write_log(self, text: str):
        if not text:
            return
        tl = text.lower()
        if tl.startswith("you:"):
            role, msg = "user", text[4:].strip()
            self.set_state("PROCESSING")
        elif tl.startswith("jarvis:"):
            role, msg = "ai", text[7:].strip()
            self.set_state("SPEAKING")
        elif tl.startswith("ai:"):
            role, msg = "ai", text[3:].strip()
            self.set_state("SPEAKING")
        elif tl.startswith("err:") or "error" in tl or "failed" in tl:
            role, msg = "err", text
        else:
            role, msg = "sys", text
        self._run_js(
            f"window.jarvisAddMessage && window.jarvisAddMessage({_js_str(role)},{_js_str(msg)});"
        )

    def set_muted(self, value: bool):
        """Force l'état mute (utilisé par wake-word)."""
        self.muted = bool(value)
        self._run_js(f"window.jarvisSetMuted && window.jarvisSetMuted({str(self.muted).lower()});")
        if self.muted:
            self.set_state("MUTED")
        else:
            self.set_state("LISTENING")

    # Phase 7.6: OSINT panel methods (called from agent.osint via ui_bridge)
    def osint_panel_start(self, target: str, mode: str, target_type: str = ""):
        self._run_js(
            f"window.osintPanelStart && window.osintPanelStart("
            f"{_js_str(target)},{_js_str(mode)},{_js_str(target_type)});"
        )

    def osint_panel_progress(self, percent: float, current: int, total: int):
        self._run_js(
            f"window.osintPanelProgress && window.osintPanelProgress({percent},{current},{total});"
        )

    def osint_panel_connector_done(self, connector: str, success: bool, count: int):
        self._run_js(
            f"window.osintPanelConnectorDone && window.osintPanelConnectorDone("
            f"{_js_str(connector)},{str(success).lower()},{count});"
        )

    def osint_panel_finding(self, ftype: str, source: str, url: str, confidence: float):
        self._run_js(
            f"window.osintPanelFinding && window.osintPanelFinding("
            f"{_js_str(ftype)},{_js_str(source)},{_js_str(url or '')},{confidence});"
        )

    def osint_panel_complete(self, report_path: str):
        self._run_js(
            f"window.osintPanelComplete && window.osintPanelComplete({_js_str(report_path)});"
        )

    def osint_panel_error(self, error: str):
        self._run_js(
            f"window.osintPanelError && window.osintPanelError({_js_str(error)});"
        )

    def osint_panel_cancel(self):
        self._run_js("window.osintPanelCancel && window.osintPanelCancel();")

    def stream_ai_chunk(self, chunk: str):
        """Append un chunk de texte à la bulle AI en cours (streaming voix-sync)."""
        if not chunk:
            return
        self._run_js(
            f"window.jarvisStreamAi && window.jarvisStreamAi({_js_str(chunk)});"
        )

    def finalize_ai_turn(self):
        """Marque la bulle AI courante comme terminée (la prochaine ouvrira une nouvelle)."""
        self._run_js("window.jarvisFinalizeAi && window.jarvisFinalizeAi();")

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")

    def wait_for_api_key(self):
        while not self._api_key_ready:
            time.sleep(0.1)

    # â”€â”€ mute â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _toggle_mute(self):
        self.muted = not self.muted
        self._run_js(f"window.jarvisSetMuted && window.jarvisSetMuted({str(self.muted).lower()});")
        if self.muted:
            self.set_state("MUTED")
            self.write_log("SYS: Microphone muted.")
        else:
            self.set_state("LISTENING")
            self.write_log("SYS: Microphone active.")

    # â”€â”€ input depuis la nouvelle UI â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _handle_user_text(self, text: str):
        text = (text or "").strip()
        if not text:
            return
        # L'UI a dÃ©jÃ  affichÃ© cÃ´tÃ© JS â†’ on dÃ©clenche juste le pipeline
        self.set_state("PROCESSING")
        cb = self.on_text_command
        if cb:
            threading.Thread(target=cb, args=(text,), daemon=True).start()

    # â”€â”€ API keys / setup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _api_keys_exist(self) -> bool:
        if not API_FILE.exists():
            return False
        if is_api_config_encrypted(API_FILE):
            return True
        try:
            loaded = load_api_config(API_FILE, prompt_if_encrypted=False)
            data = loaded.data if loaded.loaded else {}
            return bool(data.get("gemini_api_key")) and bool(data.get("os_system"))
        except Exception:
            return False

    @staticmethod
    def _detect_os() -> str:
        s = platform.system().lower()
        if s == "darwin":  return "mac"
        if s == "windows": return "windows"
        return "linux"

    def _run_setup_dialog(self):
        """Dialogue Tk modal lÃ©ger pour 1er boot (API key + OS)."""
        import tkinter as tk

        state = {"ok": False}
        root = tk.Tk()
        root.title(f"{SYSTEM_NAME} â€” Initialisation")
        root.configure(bg="#0a0e14")
        root.geometry("520x380")
        root.resizable(False, False)

        try:
            root.iconbitmap(default="")
        except Exception:
            pass

        # Centre Ã©cran
        root.update_idletasks()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"520x380+{(sw-520)//2}+{(sh-380)//2}")

        tk.Label(
            root, text=f"â—ˆ  {SYSTEM_NAME}  INITIALISATION",
            fg="#5aa0f0", bg="#0a0e14",
            font=("Consolas", 13, "bold"),
        ).pack(pady=(26, 4))

        tk.Label(
            root, text="Configure J.A.R.V.I.S. before first boot.",
            fg="#5a6a8a", bg="#0a0e14",
            font=("Consolas", 9),
        ).pack(pady=(0, 20))

        tk.Label(
            root, text="GEMINI API KEY",
            fg="#3a5a9a", bg="#0a0e14",
            font=("Consolas", 9),
        ).pack()

        key_var = tk.StringVar()
        entry = tk.Entry(
            root, textvariable=key_var, width=48, show="*",
            fg="#a3c5e8", bg="#0f141c",
            insertbackground="#a3c5e8", borderwidth=0,
            font=("Consolas", 10),
            highlightthickness=1, highlightbackground="#3a5a9a",
            highlightcolor="#5aa0f0",
        )
        entry.pack(pady=(4, 20), ipady=6)
        entry.focus_set()

        tk.Label(
            root, text="OPERATING SYSTEM",
            fg="#3a5a9a", bg="#0a0e14",
            font=("Consolas", 9),
        ).pack()

        os_var = tk.StringVar(value=self._detect_os())
        btn_frame = tk.Frame(root, bg="#0a0e14")
        btn_frame.pack(pady=(6, 18))

        os_btns = {}
        for key, label in [("windows", "WINDOWS"), ("mac", "macOS"), ("linux", "LINUX")]:
            b = tk.Button(
                btn_frame, text=label, width=12,
                font=("Consolas", 9, "bold"),
                borderwidth=0, cursor="hand2",
                command=lambda k=key: (os_var.set(k), _refresh()),
            )
            b.pack(side="left", padx=6)
            os_btns[key] = b

        def _refresh():
            for k, b in os_btns.items():
                if k == os_var.get():
                    b.configure(
                        fg="#0a0e14", bg="#5aa0f0",
                        activeforeground="#0a0e14", activebackground="#5aa0f0",
                    )
                else:
                    b.configure(
                        fg="#3a5a9a", bg="#0f141c",
                        activeforeground="#a3c5e8", activebackground="#0f141c",
                    )
        _refresh()

        def _submit(*_):
            k = key_var.get().strip()
            if not k:
                entry.configure(highlightbackground="#e04a4a", highlightcolor="#e04a4a")
                return
            os.makedirs(CONFIG_DIR, exist_ok=True)
            save_api_config(
                {"gemini_api_key": k, "os_system": os_var.get()},
                path=API_FILE,
                master_password="",
            )
            state["ok"] = True
            root.destroy()

        tk.Button(
            root, text="â–¸  INITIALISE",
            command=_submit,
            fg="#5aa0f0", bg="#0a0e14",
            activebackground="#0f141c", activeforeground="#5aa0f0",
            font=("Consolas", 10, "bold"),
            borderwidth=0, cursor="hand2",
            padx=18, pady=8,
        ).pack()

        root.bind("<Return>",    _submit)
        root.bind("<KP_Enter>",  _submit)
        root.protocol("WM_DELETE_WINDOW", lambda: os._exit(0))
        root.mainloop()

        if not state["ok"]:
            os._exit(0)
        self._api_key_ready = True


