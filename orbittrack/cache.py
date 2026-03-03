"""
Local JSON cache for calendars, tasks, and events.

Data is stored under $XDG_CACHE_HOME/orbittrack/.
The main-window will load cached data instantly on startup and then
refresh from the server in the background.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import gi
gi.require_version("GLib", "2.0")
from gi.repository import GLib

_CACHE_DIR = os.path.join(GLib.get_user_cache_dir(), "orbittrack")


def _path(name: str) -> str:
    return os.path.join(_CACHE_DIR, name)


def _read(name: str) -> dict | None:
    try:
        with open(_path(name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write(name: str, data: dict) -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    tmp = _path(name) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, _path(name))


# ── Calendars ────────────────────────────────────────────────────────────────

def load_calendars() -> list[dict[str, Any]]:
    data = _read("calendars.json")
    if data and "calendars" in data:
        return data["calendars"]
    return []


def save_calendars(calendars: list[dict[str, Any]]) -> None:
    _write("calendars.json", {"calendars": calendars, "ts": time.time()})


# ── Tasks (grouped by calendar) ──────────────────────────────────────────────

def load_task_groups() -> list[dict[str, Any]]:
    data = _read("tasks.json")
    if data and "groups" in data:
        return data["groups"]
    return []


def save_task_groups(groups: list[dict[str, Any]]) -> None:
    _write("tasks.json", {"groups": groups, "ts": time.time()})


# ── Today events (grouped by calendar) ───────────────────────────────────────

def load_today_events() -> list[dict[str, Any]]:
    data = _read("today_events.json")
    if data and "groups" in data:
        # Only return if cache is from today
        cached_date = data.get("date", "")
        from datetime import date as _date
        if cached_date == _date.today().isoformat():
            return data["groups"]
    return []


def save_today_events(groups: list[dict[str, Any]]) -> None:
    from datetime import date as _date
    _write("today_events.json", {
        "groups": groups,
        "date": _date.today().isoformat(),
        "ts": time.time(),
    })


# ── Sync tokens (per-calendar ctag / syncToken) ──────────────────────────────

def load_sync_tokens() -> dict[str, str]:
    data = _read("sync_tokens.json")
    if data and "tokens" in data:
        return data["tokens"]
    return {}


def save_sync_tokens(tokens: dict[str, str]) -> None:
    _write("sync_tokens.json", {"tokens": tokens, "ts": time.time()})


# ── Clear all cache ──────────────────────────────────────────────────────────

def clear() -> None:
    for name in ("calendars.json", "tasks.json", "today_events.json", "sync_tokens.json"):
        try:
            os.remove(_path(name))
        except Exception:
            pass
