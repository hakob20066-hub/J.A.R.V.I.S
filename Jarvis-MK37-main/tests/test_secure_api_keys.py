from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.secure_api_keys import (  # noqa: E402
    clear_session_password,
    is_api_config_encrypted,
    load_api_config,
    save_api_config,
    set_session_password,
)


def test_plain_api_config_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "api_keys.json"
        save_api_config({"gemini_api_key": "abc123456"}, path=path, master_password="")
        loaded = load_api_config(path, prompt_if_encrypted=False)
        assert loaded.loaded is True
        assert loaded.encrypted is False
        assert loaded.data.get("gemini_api_key") == "abc123456"


def test_encrypted_api_config_requires_session_password():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "api_keys.json"
        clear_session_password()
        save_api_config({"gemini_api_key": "secret_key_value"}, path=path, master_password="pw12345")
        clear_session_password()

        locked = load_api_config(path, prompt_if_encrypted=False)
        assert locked.encrypted is True
        assert locked.loaded is False

        payload = path.read_text(encoding="utf-8")
        import json
        salt = json.loads(payload)["salt"]
        set_session_password("pw12345", salt)
        unlocked = load_api_config(path, prompt_if_encrypted=False)
        assert unlocked.loaded is True
        assert unlocked.data.get("gemini_api_key") == "secret_key_value"


def test_is_api_config_encrypted_detection():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "api_keys.json"
        save_api_config({"gemini_api_key": "x"}, path=path, master_password="")
        assert is_api_config_encrypted(path) is False
        save_api_config({"gemini_api_key": "x"}, path=path, master_password="pw12345")
        assert is_api_config_encrypted(path) is True
