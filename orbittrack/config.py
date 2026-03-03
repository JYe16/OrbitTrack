"""
Credential & settings persistence.

Credentials are stored in $XDG_CONFIG_HOME/orbittrack/credentials.json.
For Flatpak this resolves to ~/.var/app/<id>/config/orbittrack/...
"""

from __future__ import annotations

import json
import os

import gi
gi.require_version("GLib", "2.0")
from gi.repository import GLib

_CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), "orbittrack")
_CRED_FILE = os.path.join(_CONFIG_DIR, "credentials.json")
_SETTINGS_FILE = os.path.join(_CONFIG_DIR, "settings.json")


# ── Credentials ─────────────────────────────────────────────────────────────

def save_credentials(url: str, username: str, password: str) -> None:
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    with open(_CRED_FILE, "w", encoding="utf-8") as f:
        json.dump({"url": url, "username": username, "password": password}, f)


def load_credentials() -> dict | None:
    try:
        with open(_CRED_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if all(k in data for k in ("url", "username", "password")):
            return data
    except Exception:
        pass
    return None


def clear_credentials() -> None:
    try:
        os.remove(_CRED_FILE)
    except Exception:
        pass


# ── Settings ─────────────────────────────────────────────────────────────────

_DEFAULTS: dict = {
    "target_calendar_id": "",
    "pomodoro_duration": 25,
    "show_completed": False,
}


def load_settings() -> dict:
    data = dict(_DEFAULTS)
    try:
        with open(_SETTINGS_FILE, encoding="utf-8") as f:
            data.update(json.load(f))
    except Exception:
        pass
    return data


def save_settings(settings: dict) -> None:
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f)
