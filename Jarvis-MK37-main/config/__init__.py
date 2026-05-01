# config/__init__.py
from pathlib import Path
from config.secure_api_keys import load_api_config

_CONFIG_PATH = Path(__file__).parent / "api_keys.json"

def get_config() -> dict:
    loaded = load_api_config(_CONFIG_PATH, prompt_if_encrypted=True)
    if loaded.loaded:
        return loaded.data
    return {}

def get_os() -> str:
    """Returns: 'windows' | 'mac' | 'linux'"""
    return get_config().get("os_system", "windows").lower()

def is_windows() -> bool: return get_os() == "windows"
def is_mac()     -> bool: return get_os() == "mac"
def is_linux()   -> bool: return get_os() == "linux"