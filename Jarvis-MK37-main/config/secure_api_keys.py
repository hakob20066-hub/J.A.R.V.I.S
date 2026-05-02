from __future__ import annotations

import base64
import getpass
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


API_CONFIG_PATH = Path(__file__).resolve().parent / "api_keys.json"
PBKDF2_ITERATIONS = 390000

_SESSION_FERNET: Optional[Fernet] = None


@dataclass
class ApiConfigState:
    encrypted: bool
    loaded: bool
    data: dict[str, Any]


def is_encrypted_payload(payload: dict[str, Any]) -> bool:
    return bool(payload.get("_encrypted") and payload.get("salt") and payload.get("token"))


def is_api_config_encrypted(path: Path = API_CONFIG_PATH) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return is_encrypted_payload(payload) if isinstance(payload, dict) else False


def set_session_password(password: str, salt_b64: str) -> None:
    global _SESSION_FERNET
    _SESSION_FERNET = _build_fernet(password=password, salt_b64=salt_b64)


def clear_session_password() -> None:
    global _SESSION_FERNET
    _SESSION_FERNET = None


def load_api_config(path: Path = API_CONFIG_PATH, prompt_if_encrypted: bool = True) -> ApiConfigState:
    if not path.exists():
        return ApiConfigState(encrypted=False, loaded=True, data={})
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ApiConfigState(encrypted=False, loaded=False, data={})
    if not isinstance(payload, dict):
        return ApiConfigState(encrypted=False, loaded=False, data={})

    if not is_encrypted_payload(payload):
        return ApiConfigState(encrypted=False, loaded=True, data=payload)

    salt_b64 = str(payload.get("salt", ""))
    token = str(payload.get("token", ""))
    if not salt_b64 or not token:
        return ApiConfigState(encrypted=True, loaded=False, data={})

    fernet = _SESSION_FERNET
    if fernet is None and prompt_if_encrypted:
        password = getpass.getpass("JARVIS API keys are encrypted. Enter master password: ")
        if password:
            fernet = _build_fernet(password=password, salt_b64=salt_b64)
            set_session_password(password=password, salt_b64=salt_b64)

    if fernet is None:
        return ApiConfigState(encrypted=True, loaded=False, data={})

    try:
        raw = fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}
        return ApiConfigState(encrypted=True, loaded=True, data=data)
    except (InvalidToken, ValueError, json.JSONDecodeError):
        return ApiConfigState(encrypted=True, loaded=False, data={})


def save_api_config(
    data: dict[str, Any],
    *,
    path: Path = API_CONFIG_PATH,
    master_password: str = "",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not master_password:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return

    salt = Fernet.generate_key()
    salt_b64 = salt.decode("utf-8")
    fernet = _build_fernet(password=master_password, salt_b64=salt_b64)
    token = fernet.encrypt(json.dumps(data, ensure_ascii=False).encode("utf-8")).decode("utf-8")
    payload = {
        "_encrypted": True,
        "kdf": "PBKDF2HMAC-SHA256",
        "iterations": PBKDF2_ITERATIONS,
        "salt": salt_b64,
        "token": token,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    set_session_password(master_password, salt_b64)


def _build_fernet(*, password: str, salt_b64: str) -> Fernet:
    salt = base64.urlsafe_b64decode(salt_b64.encode("utf-8"))
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))
    return Fernet(key)
