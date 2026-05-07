import asyncio
import re
import threading
import json
import sys
import traceback
import os
import time
from pathlib import Path

from dotenv import load_dotenv
import sounddevice as sd
from google import genai
from google.genai import types
from ui import JarvisUI
from memory import get_memory, reset_memory
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
)

from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import screen_process
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.online_presence_audit import online_presence_audit, format_audit_results
from actions.osint_lookup       import osint_lookup
from agent.wake_word import start_wake_word
from agent.bootstrap import bootstrap
from agent.mission_runner import get_runner as get_mission_runner
from agent.wake_word import start_wake_word
from agent.emergency_stop import start_emergency_stop, get_emergency_stop, reset_emergency_stop
from agent.safety_audit import register_kill_callback, audit_log
from agent.voice_router import process as route_voice, consume_async_notifications
from config.secure_api_keys import load_api_config
# route_voice retiré : on n'utilise plus le pré-routage local sur les inputs
# clavier (ça créait des doubles messages et des réponses incohérentes).
import ui_wizard


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"

# Load environment variables from .env file
load_dotenv(BASE_DIR / ".env")
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024


def _get_api_key() -> str:
    loaded = load_api_config(API_CONFIG_PATH, prompt_if_encrypted=True)
    api_key = ""
    if loaded.loaded:
        api_key = str(loaded.data.get("gemini_api_key", "")).strip()
    if api_key:
        return api_key
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if api_key:
        return api_key
    raise ValueError(
        "Gemini API key not found. Set GEMINI_API_KEY in .env or gemini_api_key in config/api_keys.json."
    )


def _is_api_key_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg for token in (
            "api key expired",
            "invalid api key",
            "api_key_invalid",
            "permission denied",
            "authentication",
            "unauthenticated",
        )
    )


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are JARVIS, Tony Stark's AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )


# ── Custom Keywords / Raccourcis ─────────────────────────────────────────────────
CUSTOM_KEYWORDS = {
    "keti": "Fais un audit de ma présence en ligne",
}

def _expand_keywords(text: str) -> str:
    """Remplace les mots-clés personnalisés par les commandes complètes."""
    text_lower = text.lower().strip()
    
    # Vérifier si le texte est un keyword exact
    if text_lower in CUSTOM_KEYWORDS:
        return CUSTOM_KEYWORDS[text_lower]
    
    # Vérifier aussi avec variantes (pluriel, etc.)
    for keyword, expansion in CUSTOM_KEYWORDS.items():
        if text_lower == keyword or text_lower == keyword + "s":
            return expansion
    
    return text


# ── Transkripsiyon temizleyici ─────────────────────────────────────────────────
_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:
    """Gemini'nin ürettiği <ctrlXX> artefaktlarını ve kontrol karakterlerini temizler."""
    # Appliquer les keywords d'abord
    text = _expand_keywords(text)
    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()


# ── Tool declarations ──────────────────────────────────────────────────────────
TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, stay SILENT — the vision module speaks directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command. NEVER route to agent_task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands. NEVER use for Steam/Epic — use game_updater."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "online_presence_audit",
        "description": "Audits your public online presence. Finds all your accounts across TikTok, Twitter, YouTube, Twitch, GitHub, LinkedIn, etc. based on your Instagram handle and aliases.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "instagram_handle": {"type": "STRING", "description": "Your Instagram handle (with or without @)"},
                "aliases": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Other usernames/aliases you use (optional)"}
            },
            "required": ["instagram_handle"]
        }
    },
    {
        "name": "osint_lookup",
        "description": (
            "OSINT lookup unifié. **APPELLE CE TOOL IMMÉDIATEMENT** dès que tu vois "
            "le mot 'osint', 'lookup', 'audit', 'renseignement', 'fait une recherche "
            "sur X', 'cherche des infos sur X', 'trouve moi tout sur X' — quelle que "
            "soit la cible (email, domaine, IP, username, téléphone, hash crypto). "
            "NE POSE PAS de questions de clarification : extrais la cible du prompt "
            "et appelle le tool directement. "
            "Combine 26 connecteurs Python (crt.sh, HIBP, Shodan, VirusTotal, GitHub, "
            "Hunter.io, etc.) + 36 wrappers Kali (sherlock, theHarvester, nuclei…) "
            "+ 4 analyzers (behavior/network/timeline/metadata) + rapport HTML auto-généré."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "target": {
                    "type": "STRING",
                    "description": "La cible : email, domaine (example.com), IP, username, téléphone (+33...), hash crypto."
                },
                "mode": {
                    "type": "STRING",
                    "description": "self_audit (cible self déclarée au wizard) ou external_target (tiers — exige consent=true et limité à 5/jour). Par défaut self_audit.",
                    "enum": ["self_audit", "external_target"]
                },
                "depth": {
                    "type": "INTEGER",
                    "description": "Profondeur de la cascade pivot (1-3). Par défaut 2."
                },
                "deep": {
                    "type": "BOOLEAN",
                    "description": "Active les modes étendus (face-recognition refusée par défaut). Par défaut false."
                },
                "consent": {
                    "type": "BOOLEAN",
                    "description": "True si l'user a confirmé le disclaimer RGPD pour external_target. Par défaut false."
                }
            },
            "required": ["target"]
        }
    },
    {
        "name": "shutdown_jarvis",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop Jarvis. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
]


class JarvisLive:

    def __init__(self, ui: JarvisUI):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self._auth_error_notified = False
        self.ui.on_text_command = self._on_text_command
        self._turn_done_event: asyncio.Event | None = None
        self._text_turn_pending = False  # True quand le tour user vient du clavier (skip echo input_transcription)
        self._wake_word_active = False   # True si un backend wake-word a démarré (mute par défaut)
        
        # Phase 7.5: Safety Net
        self._demo_mode = False
        self._last_action = None
        self._action_lock = threading.Lock()
        self._emergency_stop = get_emergency_stop()
        
        # Phase 7: Eviter les notifications répétées
        self._last_notification_check = 0
        self._notification_cooldown = 5.0  # 5 secondes entre les vérifications
        
        # Mémoire 4 couches
        self.memory = get_memory()
        self._session_token_count = 0

    def _log_episode(self, event_type: str, summary: str, details: dict = None, entities: list = None):
        """Enregistre un événement dans la mémoire episodic."""
        try:
            self.memory.write_episode(
                event_type=event_type,
                summary=summary,
                details=details or {},
                entities=entities or [],
            )
        except Exception as e:
            print(f"[Memory] Error logging episode: {e}")

    def _update_ui_stats(self):
        """Met à jour les stats mémoire dans l'UI."""
        try:
            stats = self.memory.stats()
            self.ui.set_memory_stats(stats)
        except Exception as e:
            print(f"[Memory] Error updating stats: {e}")

    def _add_turn_to_memory(self, role: str, content: str, metadata: dict = None):
        """Ajoute un tour à la working memory."""
        try:
            self.memory.add_turn(role, content, **(metadata or {}))
            self._update_ui_stats()
        except Exception as e:
            print(f"[Memory] Error adding turn: {e}")

    def _on_text_command(self, text: str):
        # Le message utilisateur va DIRECTEMENT à Gemini Live (qui parle + tools).
        # NE PAS pré-router via route_voice() ici : ça générait une réponse locale
        # qu'on renvoyait ensuite comme prompt user → Gemini répondait à sa propre
        # sortie (double message, incohérent, voix qui décroche).
        if not self._loop or not self.session:
            return
        # NE PAS write_log ici : ui.html (sendText) a déjà appelé addMessage('user', text)
        # côté JS — sinon le message apparaît en double.
        # Marque le tour comme texte → on skip l'écho input_transcription au turn_complete
        # (Gemini renvoie le texte envoyé comme transcription, ce qui produirait
        # une deuxième bulle [USER] si on le re-loggait).
        self._text_turn_pending = True
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    async def _consume_async_notifs_loop(self):
        """
        Phase 7 gap #1 : poll régulier de la queue d'async notifications du
        voice_router (missions terminées, alertes background, etc.) et fait
        parler Jarvis dessus.

        Phase 7 gap #2 : mutex doux — on diffère l'annonce si :
          - Jarvis est en train de parler (`_is_speaking`)
          - L'user a parlé dans les 3 dernières secondes
          - Un tour texte est en attente (`_text_turn_pending`)
        Sinon le TTS auto pourrait chevaucher la voix de l'user.
        """
        from agent.voice_router import consume_async_notifications
        import time as _t

        print("[JARVIS] 🟣[MISSION] async-notif loop started (poll 5s)")
        while True:
            await asyncio.sleep(5.0)
            try:
                pending: list[str] = []
                # Drain seulement si personne ne parle. Sinon on laisse en queue.
                with self._speaking_lock:
                    jarvis_speaking = self._is_speaking
                user_active = _t.time() < self._user_speaking_until
                if jarvis_speaking or user_active or self._text_turn_pending:
                    continue

                pending = consume_async_notifications()
                if not pending:
                    continue

                # Mutex sur l'envoi TTS — évite course concurrente
                with self._tts_lock:
                    text = " ".join(pending)
                    print(f"[JARVIS] 🟣[MISSION] announcing {len(pending)} notif(s)")
                    self.ui.write_log(f"AI: {text}")
                    self.speak(text)
            except Exception as e:
                print(f"[JARVIS] ⚠️ async-notif loop error: {e}")

    def _setup_wake_word(self):
        """Wake word 'Jarvis'. Si backend dispo, mic muet par défaut.
        L'user dit "Jarvis" → mic ON. Après réponse → remute. Style Siri."""
        def on_wake(keyword: str):
            print(f"[JARVIS] 🟢 Wake: '{keyword}' — mic ON")
            self.ui.set_muted(False)

        try:
            detector = start_wake_word(on_detect=on_wake, keyword="jarvis")
            backend = getattr(detector, "_backend", "none")
            if backend != "none":
                self._wake_word_active = True
                self.ui.set_muted(True)  # silencieux jusqu'à ce qu'on dise "Jarvis"
                self.ui.write_log(f"SYS: Wake word actif (backend={backend}). Dis 'Jarvis' pour parler.")
            else:
                self._wake_word_active = False
                self.ui.set_muted(False)
                self.ui.write_log("SYS: Aucun backend wake-word — micro toujours actif.")
        except Exception as e:
            print(f"[JARVIS] ⚠️ wake_word setup failed: {e}")
            self._wake_word_active = False
            self.ui.set_muted(False)

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    # Phase 7.5: Safety Net Methods
    def set_demo_mode(self, enabled: bool) -> None:
        """Active/désactive le mode demo."""
        with self._action_lock:
            self._demo_mode = enabled
            status = "activé" if enabled else "désactivé"
            self.ui.write_log(f"SYS: Demo mode {status}")
            self._emergency_stop._log_event("DEMO_MODE_TOGGLE", f"Demo mode {status}")

    def get_demo_mode(self) -> bool:
        """Retourne l'état du mode demo."""
        return self._demo_mode

    def get_emergency_status(self) -> dict:
        """Retourne le statut du système d'urgence."""
        return self._emergency_stop.get_status()

    def trigger_emergency_stop(self) -> None:
        """Déclenche manuellement l'arrêt d'urgence."""
        self._emergency_stop._emergency_trigger()
        self.ui.write_log("SYS: Emergency stop triggered manually")

    def get_last_action(self) -> dict:
        """Retourne la dernière action exécutée."""
        with self._action_lock:
            return self._last_action

    def rollback_last_action(self) -> str:
        """Tente d'annuler la dernière action."""
        with self._action_lock:
            if not self._last_action:
                return "No action to rollback"
            
            action = self._last_action
            try:
                # Log rollback attempt
                self._emergency_stop._log_event("ROLLBACK_ATTEMPT", f"Rolling back: {action.get('description', 'Unknown')}")
                
                # Implémenter le rollback selon le type d'action
                if action.get('type') == 'keyboard':
                    # Envoyer Ctrl+Z
                    import pyautogui
                    pyautogui.hotkey('ctrl', 'z')
                    result = "Keyboard action rolled back (Ctrl+Z)"
                elif action.get('type') == 'mouse_click':
                    result = "Mouse click cannot be rolled back automatically"
                elif action.get('type') == 'file_delete':
                    # Tenter de restaurer depuis la corbeille (Windows)
                    try:
                        import send2trash
                        # Note: send2trash ne permet pas de restaurer facilement
                        result = "File deleted - check recycle bin for manual restore"
                    except ImportError:
                        result = "File delete rollback not available"
                else:
                    result = f"Rollback not implemented for action type: {action.get('type', 'unknown')}"
                
                # Log result
                self._emergency_stop._log_event("ROLLBACK_RESULT", result)
                self.ui.write_log(f"SYS: {result}")
                
                # Effacer l'action après rollback
                self._last_action = None
                return result
                
            except Exception as e:
                error_msg = f"Rollback failed: {e}"
                self._emergency_stop._log_event("ROLLBACK_ERROR", error_msg)
                self.ui.write_log(f"ERR: {error_msg}")
                return error_msg

    def _track_action(self, action_type: str, description: str, details: dict = None) -> None:
        """Enregistre une action pour le rollback."""
        with self._action_lock:
            self._last_action = {
                'type': action_type,
                'description': description,
                'details': details or {},
                'timestamp': time.time()
            }

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        # Ancienne mémoire pour backward compat
        old_memory     = load_memory()
        mem_str        = format_memory_for_prompt(old_memory)
        
        # Nouvelle mémoire: RAG retrieval si query disponible
        rag_context = ""
        try:
            # Récupère les derniers episodes + facts pour contexte
            recent_eps = self.memory.get_recent_episodes(n=3)
            recent_facts = self.memory.get_facts_by_category("identity")
            
            rag_lines = ["[RECENT MEMORY]"]
            for ep in recent_eps:
                rag_lines.append(f"- [{ep.type}] {ep.summary}")
            for fact in recent_facts[:5]:
                rag_lines.append(f"- {fact.key}: {fact.value}")
            rag_context = "\n".join(rag_lines) + "\n\n" if rag_lines else ""
        except Exception as e:
            print(f"[Memory] Error building RAG context: {e}")
        
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        parts = [time_ctx, rag_context]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[JARVIS] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        # Phase 7.5: Vérifier l'état d'urgence et le mode demo
        if self._emergency_stop.is_emergency_active():
            error_msg = "Emergency stop active - all actions blocked"
            print(f"[JARVIS] 🚨 {error_msg}")
            self.ui.write_log(f"ERR: {error_msg}")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"error": error_msg}
            )

        # Phase 7.5: Mode demo - logging sans exécution pour les actions sensibles
        demo_actions = ["computer_control", "browser_control", "file_controller", "desktop_control"]
        if self._demo_mode and name in demo_actions:
            demo_msg = f"[DEMO] Would execute {name} with args: {args}"
            print(f"[JARVIS] 🎭 {demo_msg}")
            self.ui.write_log(demo_msg)
            self._emergency_stop._log_event("DEMO_ACTION", f"{name}: {args}")
            # Tracker l'action pour le mode demo
            self._track_action(name, f"Demo: {name}", args)
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": f"Demo mode: {name} action logged but not executed"}
            )

        # ── save_memory: sessiz ve hızlı ──────────────────────────────────────
        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "open_app":
                r = await loop.run_in_executor(None, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "weather_report":
                r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_message":
                r = await loop.run_in_executor(None, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "reminder":
                r = await loop.run_in_executor(None, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "screen_process":
                threading.Thread(
                    target=screen_process,
                    kwargs={"parameters": args, "response": None,
                            "player": self.ui, "session_memory": None},
                    daemon=True
                ).start()
                result = "Vision module activated. Stay completely silent — vision module will speak directly."

            elif name == "computer_control":
                # Phase 7.5: Tracker l'action pour rollback
                action = args.get('action', '')
                if action in ['type', 'click', 'double_click', 'right_click', 'hotkey']:
                    self._track_action('keyboard' if action in ['type', 'hotkey'] else 'mouse_click', 
                                     f"Computer control: {action}", args)
                r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id  = get_queue().submit(goal=args.get("goal", ""), priority=priority, speak=self.speak)
                result   = f"Task started (ID: {task_id})."

            elif name == "web_search":
                r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "online_presence_audit":
                instagram = args.get("instagram_handle", "").replace("@", "")
                aliases = args.get("aliases", [])
                r = await loop.run_in_executor(None, lambda: online_presence_audit(instagram, aliases))
                formatted = format_audit_results(r)
                self.ui.write_log(formatted)
                result = formatted

            elif name == "osint_lookup":
                r = await loop.run_in_executor(
                    None,
                    lambda: osint_lookup(parameters=args, player=self.ui)
                )
                self.ui.write_log(r or "OSINT: aucun résultat.")
                result = r or "OSINT lookup completed (no findings)."

            elif name == "shutdown_jarvis":
                self.ui.write_log("SYS: Shutdown requested.")
                self.speak("Goodbye, sir.")
                def _shutdown():
                    import time, os
                    time.sleep(1)
                    os._exit(0)
                threading.Thread(target=_shutdown, daemon=True).start()

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                jarvis_speaking = self._is_speaking
            if not jarvis_speaking and not self.ui.muted:
                data = indata.tobytes()
                loop.call_soon_threadsafe(
                    self.out_queue.put_nowait,
                    {"data": data, "mime_type": "audio/pcm"}
                )

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                print("[JARVIS] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[JARVIS] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():

                    if response.data:
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                # Stream chaque chunk vers la bulle AI : la cadence
                                # des chunks est alignée sur la voix → écriture
                                # synchronisée avec la lecture audio.
                                self.ui.stream_ai_chunk(txt)
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                # Stream live : la transcription user apparaît
                                # AVANT que Jarvis réponde (sinon les chunks
                                # n'arrivent qu'au turn_complete, donc après la
                                # réponse). Skip si vient du clavier (déjà affiché).
                                if not self._text_turn_pending:
                                    self.ui.stream_user_chunk(txt)
                                in_buf.append(txt)
                                # Phase 7 gap #2 : marque l'user comme actif pour
                                # ~3s — bloque les annonces async pendant qu'il parle.
                                import time as _t
                                self._user_speaking_until = _t.time() + 3.0

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            # Bulle user finalisée (déjà streamée ci-dessus)
                            self.ui.finalize_user_turn()
                            self._text_turn_pending = False
                            in_buf = []

                            # Bulle AI streamée chunk par chunk → on la finalise.
                            self.ui.finalize_ai_turn()
                            out_buf = []

                            # Wake-word actif : Jarvis a fini → remute, redire
                            # "Jarvis" pour relancer (Siri-style).
                            if self._wake_word_active:
                                self.ui.set_muted(True)
                            # Phase 7: Vérifier les notifications asynchrones (missions terminées)
                            try:
                                current_time = time.time()
                                if current_time - self._last_notification_check >= self._notification_cooldown:
                                    notifications = consume_async_notifications()
                                    if notifications:
                                        for notif in notifications:
                                            # Ajouter à la mémoire working
                                            self._add_turn_to_memory("assistant", notif, {"type": "async_notification"})
                                            # Annoncer via TTS
                                            self.speak(notif)
                                            self.ui.write_log(f"ASYNC: {notif}")
                                    self._last_notification_check = current_time
                            except Exception as e:
                                print(f"[JARVIS] ⚠️ Error consuming async notifications: {e}")

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[JARVIS] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )

        except Exception as e:
            print(f"[JARVIS] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play started")

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        )
        stream.start()

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue

                self.set_speaking(True)
                await asyncio.to_thread(stream.write, chunk)

        except Exception as e:
            print(f"[JARVIS] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    async def run(self):
        while True:
            retry_delay = 3
            try:
                client = genai.Client(
                    api_key=_get_api_key(),
                    http_options={"api_version": "v1beta"}
                )
                print("[JARVIS] 🔌 Connecting...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session        = session
                    self._loop          = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue      = asyncio.Queue(maxsize=10)
                    self._turn_done_event = asyncio.Event()

                    print("[JARVIS] ✅ Connected.")
                    self._auth_error_notified = False
                    self.ui.write_log("SYS: JARVIS online.")
                    self._setup_wake_word()

                    # Wake word : démarre le détecteur. Si un backend est dispo,
                    # le micro reste muet par défaut, "Jarvis" l'active. Sinon,
                    # fallback : micro toujours ouvert (comportement précédent).
                    self._setup_wake_word()

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._consume_async_notifs_loop())

            except Exception as e:
                if _is_api_key_error(e):
                    retry_delay = 10
                    self.ui.set_state("ERROR")
                    if not self._auth_error_notified:
                        self.ui.write_log(
                            "ERR: Gemini API key invalide ou expiree. Mets a jour config/api_keys.json ou .env."
                        )
                        self._auth_error_notified = True
                    print(f"[JARVIS] ⚠️ API key error: {e}")
                else:
                    print(f"[JARVIS] ⚠️ {e}")
                    traceback.print_exc()

            self.set_speaking(False)
            if retry_delay == 3:
                self.ui.set_state("THINKING")
            print(f"[JARVIS] 🔄 Reconnecting in {retry_delay}s...")
            await asyncio.sleep(retry_delay)


def main():
    boot = bootstrap(skip_warmup=True)
    print(f"[Bootstrap] 🟢[FAST] status={boot.get('status')} needs_wizard={boot.get('needs_wizard')}")
    if boot.get("needs_wizard"):
        try:
            ui_wizard.run()
        except Exception as e:
            print(f"[Bootstrap] ⚠️ wizard failed: {e} — continuing in degraded mode.")

    # Modèle local : check rapide via /api/tags (instant). Si déjà installé,
    # on skip le pull → boot rapide. Sinon on lance le pull en BG pour ne pas
    # bloquer le démarrage UI ; les missions Ollama échoueront jusqu'à ce que
    # le pull soit fini, mais le reste de Jarvis est utilisable immédiatement.
    try:
        from agent.local_llm_provider import get_local_provider, ensure_model_installed
        provider = get_local_provider()
        if hasattr(provider, "is_model_installed") and provider.is_model_installed():
            print(f"[Bootstrap] ✅ Local model already installed ({provider.model}) — skip pull.")
        else:
            print(f"[Bootstrap] 🟢[FAST] Local model missing — pulling in background ({provider.model})...")
            def _bg_pull():
                try:
                    ensure_model_installed(
                        on_progress=lambda p, m: print(f"[Bootstrap] {m}"),
                    )
                    print("[Bootstrap] ✅ Local model ready (BG).")
                except Exception as e:
                    print(f"[Bootstrap] ⚠️ BG pull failed: {e}")
            threading.Thread(target=_bg_pull, daemon=True, name="bootstrap-pull").start()
    except Exception as e:
        print(f"[Bootstrap] ⚠️ Local model check failed: {e}")

    mission_runner_instance = get_mission_runner()
    mission_runner_instance.start()

    # Phase 7.5 — Safety Net : kill switch global Ctrl+Alt+Esc
    register_kill_callback(lambda: mission_runner_instance.stop(wait=False))
    audit_log("boot_complete", {"status": boot.get("status")})
    start_emergency_stop()

    ui = JarvisUI("face.png")

    def voice_loop_runner():
        ui.wait_for_api_key()
        jarvis = JarvisLive(ui)
        # Phase 7.5: Lier JarvisLive à l'UI pour les callbacks de sécurité
        ui._jarvis_instance = jarvis
        try:
            asyncio.run(jarvis.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")
        finally:
            # Nettoyer l'emergency stop à l'arrêt
            jarvis._emergency_stop.shutdown()

    threading.Thread(target=voice_loop_runner, daemon=True).start()
    ui.root.mainloop()


if __name__ == "__main__":
    main()
