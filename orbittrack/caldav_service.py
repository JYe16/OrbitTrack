"""
CalDAV service module – handles all interactions with the CalDAV server.
"""

from __future__ import annotations

import caldav
from datetime import datetime, timezone, timedelta, date
from typing import Any
import uuid
import re
from caldav.elements.base import BaseElement


class _AppleCalendarColor(BaseElement):
    tag = "{http://apple.com/ns/ical/}calendar-color"


class _CaldavCalendarColor(BaseElement):
    tag = "{urn:ietf:params:xml:ns:caldav}calendar-color"


class _CalendarServerCalendarColor(BaseElement):
    tag = "{http://calendarserver.org/ns/}calendar-color"


class _NextcloudCalendarColor(BaseElement):
    tag = "{http://nextcloud.com/ns}calendar-color"


def _normalize_color(raw: str | None, default: str = "#4A90D9") -> str:
    """Normalize a calendar color value.

    NextCloud (and Apple) often return colors with an alpha suffix,
    e.g. ``#FF0000FF`` (9 chars) or ``#FF0000`` (7 chars).
    CSS ``background`` works with 4/7-char hex but NOT 9-char,
    so we strip the alpha portion when present.
    """
    if not raw or not isinstance(raw, str):
        logger.info("Calendar color missing or not a string: %r → using default", raw)
        return default
    raw = raw.strip()

    # Accept values without '#', e.g. "FF0000" or "FF0000FF"
    if re.fullmatch(r'[0-9a-fA-F]{6}([0-9a-fA-F]{2})?', raw):
        raw = f"#{raw}"
    elif re.fullmatch(r'[0-9a-fA-F]{3}([0-9a-fA-F])?', raw):
        raw = f"#{raw}"

    # Match #RRGGBB or #RRGGBBAA
    m = re.match(r'^(#[0-9a-fA-F]{6})([0-9a-fA-F]{2})?$', raw)
    if m:
        result = m.group(1)
        logger.info("Calendar color raw=%r → normalized=%r", raw, result)
        return result
    # Match short form #RGB or #RGBA
    m2 = re.match(r'^(#[0-9a-fA-F]{3})[0-9a-fA-F]?$', raw)
    if m2:
        result = m2.group(1)
        logger.info("Calendar color raw=%r → normalized=%r (short)", raw, result)
        return result
    logger.warning("Calendar color unrecognized format: %r → using default", raw)
    return default


def _extract_color_candidate(value: Any) -> str | None:
    """Extract a color-looking token from mixed CalDAV property value types."""
    if value is None:
        return None

    text = None
    if isinstance(value, str):
        text = value
    elif hasattr(value, "text") and isinstance(value.text, str):
        text = value.text
    else:
        try:
            text = str(value)
        except Exception:
            text = None

    if not text:
        return None

    text = text.strip()
    match = re.search(r"#[0-9a-fA-F]{3,8}", text)
    if match:
        return match.group(0)

    # Some servers return plain hex without leading '#'
    plain_hex = re.search(r"\b[0-9a-fA-F]{6}([0-9a-fA-F]{2})?\b", text)
    if plain_hex:
        return plain_hex.group(0)

    return text if text.startswith("#") else None


def _get_calendar_color(cal, default: str = "#4A90D9") -> str:
    """Extract calendar color from common CalDAV property variants."""
    prop_elements = (
        _AppleCalendarColor(),
        _CaldavCalendarColor(),
        _CalendarServerCalendarColor(),
        _NextcloudCalendarColor(),
    )
    prop_keys = tuple(el.tag for el in prop_elements) + ("calendar-color",)

    try:
        props = cal.get_properties(list(prop_elements))
        if isinstance(props, dict):
            for key in prop_keys:
                if key in props and props[key]:
                    candidate = _extract_color_candidate(props[key])
                    if candidate:
                        return _normalize_color(candidate, default)
            for value in props.values():
                candidate = _extract_color_candidate(value)
                if candidate:
                    return _normalize_color(candidate, default)
    except Exception:
        pass

    for element in prop_elements:
        try:
            value = cal.get_property(element)
            candidate = _extract_color_candidate(value)
            if candidate:
                return _normalize_color(candidate, default)
        except Exception:
            continue

    try:
        for attr in ("color", "calendar_color", "calendarColor"):
            raw = getattr(cal, attr, None)
            if raw:
                return _normalize_color(str(raw), default)
    except Exception:
        pass

    return default


import logging
logger = logging.getLogger(__name__)


def _connect(url: str, username: str, password: str) -> caldav.DAVClient:
    """Create a CalDAV client and return it."""
    return caldav.DAVClient(url=url, username=username, password=password)


def get_calendar_ctags(
    url: str, username: str, password: str
) -> dict[str, str]:
    """Return a mapping of calendar_id → ctag (or getctag / sync-token).

    This is a lightweight PROPFIND that does NOT download any events or
    tasks.  The caller can compare ctags with the previous run to decide
    whether a full re-fetch is necessary.
    """
    client = _connect(url, username, password)
    principal = client.principal()
    calendars = principal.calendars()
    result: dict[str, str] = {}

    for cal in calendars:
        cal_id = str(cal.url)
        tag = ""
        # Try several common properties
        for prop_name in ("getctag", "sync-token", "sync_token"):
            try:
                val = cal.get_property(prop_name)
                if val:
                    tag = str(val).strip()
                    break
            except Exception:
                pass
        if not tag:
            # Fallback: use the ETag of the calendar collection itself
            try:
                tag = str(getattr(cal, "etag", "") or "")
            except Exception:
                pass
        result[cal_id] = tag

    return result


def _parse_iso_datetime(value: str) -> datetime:
    """Parse ISO datetime, including UTC 'Z' suffix for Python 3.10 compatibility."""
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    return datetime.fromisoformat(normalized)


def _to_vobject_utc_naive(value: datetime) -> datetime:
    """Convert datetime to UTC-naive for vobject serialization compatibility."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def verify_credentials(url: str, username: str, password: str) -> bool:
    """Return True if we can reach the CalDAV principal."""
    try:
        client = _connect(url, username, password)
        client.principal()
        return True
    except Exception:
        return False


def list_calendars(url: str, username: str, password: str) -> list[dict[str, Any]]:
    """Return a list of calendars with id, name, color and supported components."""
    client = _connect(url, username, password)
    principal = client.principal()
    calendars = principal.calendars()
    result = []
    for cal in calendars:
        props = {"id": str(cal.url), "name": cal.name or "Unnamed"}
        props["color"] = _get_calendar_color(cal)
        try:
            supported = cal.get_supported_components()
            props["supports_events"] = "VEVENT" in supported
            props["supports_todos"] = "VTODO" in supported
        except Exception:
            props["supports_events"] = True
            props["supports_todos"] = True
        result.append(props)
    return result


def _parse_rrule(vtodo) -> dict[str, Any] | None:
    """Extract RRULE info from a VTODO component."""
    try:
        if hasattr(vtodo, "rrule"):
            rrule_str = str(vtodo.rrule.value)
            result = {"raw": rrule_str}
            parts = rrule_str.split(";")
            for part in parts:
                if "=" in part:
                    key, val = part.split("=", 1)
                    result[key.lower()] = val
            return result
    except Exception:
        pass
    return None


def _parse_due(vtodo) -> str | None:
    """Extract DUE date from a VTODO component."""
    try:
        if hasattr(vtodo, "due"):
            due_val = vtodo.due.value
            if isinstance(due_val, datetime):
                return due_val.isoformat()
            elif isinstance(due_val, date):
                return due_val.isoformat()
    except Exception:
        pass
    return None


def list_tasks(
    url: str,
    username: str,
    password: str,
    show_completed: bool = False,
) -> list[dict[str, Any]]:
    """Return tasks grouped by calendar."""
    client = _connect(url, username, password)
    principal = client.principal()
    calendars = principal.calendars()

    grouped: list[dict[str, Any]] = []
    for cal in calendars:
        try:
            supported = cal.get_supported_components()
            if "VTODO" not in supported:
                continue
        except Exception:
            pass

        try:
            todos = cal.todos(include_completed=show_completed)
        except Exception:
            continue

        tasks = []
        for todo in todos:
            try:
                vtodo = todo.vobject_instance.vtodo
                summary = str(vtodo.summary.value) if hasattr(vtodo, "summary") else "Untitled"
                status = str(vtodo.status.value) if hasattr(vtodo, "status") else "NEEDS-ACTION"
                uid = str(vtodo.uid.value) if hasattr(vtodo, "uid") else str(uuid.uuid4())
                priority = int(vtodo.priority.value) if hasattr(vtodo, "priority") else 0
                due = _parse_due(vtodo)
                rrule = _parse_rrule(vtodo)

                description = ""
                try:
                    if hasattr(vtodo, "description"):
                        description = str(vtodo.description.value)
                except Exception:
                    pass

                tasks.append(
                    {
                        "uid": uid,
                        "summary": summary,
                        "status": status,
                        "priority": priority,
                        "due": due,
                        "description": description,
                        "recurring": rrule is not None,
                        "rrule": rrule,
                        "calendar_id": str(cal.url),
                    }
                )
            except Exception:
                continue

        color = _get_calendar_color(cal)

        grouped.append(
            {
                "calendar_id": str(cal.url),
                "calendar_name": cal.name or "Unnamed",
                "calendar_color": color,
                "tasks": tasks,
            }
        )

    return grouped


# ── Task CRUD ──────────────────────────────────────────────────────────────

def create_task(
    url: str,
    username: str,
    password: str,
    calendar_id: str,
    summary: str,
    description: str = "",
    due: str | None = None,
    priority: int = 0,
) -> dict[str, Any]:
    """Create a new VTODO in the specified calendar."""
    client = _connect(url, username, password)
    calendar = caldav.Calendar(client=client, url=calendar_id)

    task_uid = str(uuid.uuid4())
    now_stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

    due_line = ""
    if due:
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", due.strip()):
                due_date = date.fromisoformat(due.strip())
                due_line = f"\nDUE;VALUE=DATE:{due_date.strftime('%Y%m%d')}"
            else:
                due_dt = datetime.fromisoformat(due)
                if due_dt.tzinfo:
                    due_line = f"\nDUE:{due_dt.strftime('%Y%m%dT%H%M%SZ')}"
                else:
                    due_line = f"\nDUE:{due_dt.strftime('%Y%m%dT%H%M%S')}"
        except Exception:
            pass

    desc_line = f"\nDESCRIPTION:{description}" if description else ""

    vcal = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//OrbitTrack//EN
BEGIN:VTODO
UID:{task_uid}
DTSTAMP:{now_stamp}
CREATED:{now_stamp}
SUMMARY:{summary}
STATUS:NEEDS-ACTION
PRIORITY:{priority}{due_line}{desc_line}
END:VTODO
END:VCALENDAR"""

    calendar.save_todo(vcal)
    return {"uid": task_uid, "summary": summary, "status": "NEEDS-ACTION"}


def update_task(
    url: str,
    username: str,
    password: str,
    calendar_id: str,
    task_uid: str,
    summary: str | None = None,
    status: str | None = None,
    description: str | None = None,
    due: str | None = None,
    priority: int | None = None,
) -> dict[str, Any]:
    """Update an existing VTODO. Handles recurring tasks properly."""
    client = _connect(url, username, password)

    candidate_calendars: list[Any] = []
    seen_calendar_ids: set[str] = set()

    def add_calendar(cal_obj: Any) -> None:
        cal_id = str(getattr(cal_obj, "url", ""))
        if not cal_id or cal_id in seen_calendar_ids:
            return
        seen_calendar_ids.add(cal_id)
        candidate_calendars.append(cal_obj)

    if calendar_id:
        try:
            add_calendar(caldav.Calendar(client=client, url=calendar_id))
        except Exception:
            pass

    try:
        principal = client.principal()
        for cal in principal.calendars():
            try:
                supported = cal.get_supported_components()
                if "VTODO" not in supported:
                    continue
            except Exception:
                pass
            add_calendar(cal)
    except Exception:
        pass

    todo_obj = None
    for calendar in candidate_calendars:
        try:
            results = calendar.search(todo=True, uid=task_uid)
            if results:
                todo_obj = results[0]
                break
        except Exception:
            pass

        try:
            for t in calendar.todos(include_completed=True):
                try:
                    if str(t.vobject_instance.vtodo.uid.value) == task_uid:
                        todo_obj = t
                        break
                except Exception:
                    continue
            if todo_obj:
                break
        except Exception:
            continue

    if not todo_obj:
        raise ValueError(f"Task {task_uid} not found")

    vtodo = todo_obj.vobject_instance.vtodo
    is_recurring = hasattr(vtodo, "rrule")

    if summary is not None:
        if hasattr(vtodo, "summary"):
            vtodo.summary.value = summary
        else:
            vtodo.add("summary").value = summary

    if description is not None:
        if hasattr(vtodo, "description"):
            vtodo.description.value = description
        else:
            vtodo.add("description").value = description

    if priority is not None:
        if hasattr(vtodo, "priority"):
            vtodo.priority.value = str(priority)
        else:
            vtodo.add("priority").value = str(priority)

    if due is not None:
        try:
            due_text = due.strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", due_text):
                due_value: date | datetime = date.fromisoformat(due_text)
            else:
                due_value = _to_vobject_utc_naive(datetime.fromisoformat(due_text))

            if hasattr(vtodo, "due"):
                vtodo.due.value = due_value
            else:
                vtodo.add("due").value = due_value
        except Exception:
            pass

    if status is not None:
        if status == "COMPLETED":
            if is_recurring:
                try:
                    todo_obj.complete()
                    return {
                        "uid": task_uid,
                        "status": "COMPLETED",
                        "recurring": True,
                        "message": "Recurring task completed, next occurrence created",
                    }
                except Exception:
                    pass

            if hasattr(vtodo, "status"):
                vtodo.status.value = "COMPLETED"
            else:
                vtodo.add("status").value = "COMPLETED"
            now_stamp = _to_vobject_utc_naive(datetime.now(timezone.utc))
            if hasattr(vtodo, "completed"):
                vtodo.completed.value = now_stamp
            else:
                vtodo.add("completed").value = now_stamp
            if hasattr(vtodo, "percent_complete"):
                vtodo.percent_complete.value = "100"
        elif status == "NEEDS-ACTION":
            if hasattr(vtodo, "status"):
                vtodo.status.value = "NEEDS-ACTION"
            else:
                vtodo.add("status").value = "NEEDS-ACTION"
            try:
                if hasattr(vtodo, "completed"):
                    del vtodo.contents["completed"]
            except Exception:
                pass

    # Update LAST-MODIFIED
    try:
        now_stamp = _to_vobject_utc_naive(datetime.now(timezone.utc))
        if hasattr(vtodo, "last_modified"):
            vtodo.last_modified.value = now_stamp
        else:
            vtodo.add("last-modified").value = now_stamp
    except Exception:
        pass

    todo_obj.save()

    return {
        "uid": task_uid,
        "summary": str(vtodo.summary.value) if hasattr(vtodo, "summary") else "",
        "status": str(vtodo.status.value) if hasattr(vtodo, "status") else "NEEDS-ACTION",
        "recurring": is_recurring,
    }


def delete_task(
    url: str,
    username: str,
    password: str,
    calendar_id: str,
    task_uid: str,
) -> dict[str, str]:
    """Delete a VTODO from the calendar."""
    client = _connect(url, username, password)
    calendar = caldav.Calendar(client=client, url=calendar_id)

    todo_obj = None
    try:
        results = calendar.search(todo=True, uid=task_uid)
        if results:
            todo_obj = results[0]
    except Exception:
        pass

    if not todo_obj:
        for t in calendar.todos(include_completed=True):
            try:
                if str(t.vobject_instance.vtodo.uid.value) == task_uid:
                    todo_obj = t
                    break
            except Exception:
                continue

    if not todo_obj:
        raise ValueError(f"Task {task_uid} not found")

    todo_obj.delete()
    return {"uid": task_uid, "deleted": True}


# ── Events ─────────────────────────────────────────────────────────────────

def create_event(
    url: str,
    username: str,
    password: str,
    calendar_id: str,
    summary: str,
    dtstart: str,
    dtend: str,
) -> dict[str, str]:
    """Create a VEVENT in the specified calendar."""
    client = _connect(url, username, password)
    calendar = caldav.Calendar(client=client, url=calendar_id)

    event_uid = str(uuid.uuid4())
    start_dt = _parse_iso_datetime(dtstart)
    end_dt = _parse_iso_datetime(dtend)

    vcal = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//OrbitTrack//EN
BEGIN:VEVENT
UID:{event_uid}
DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}
DTSTART:{start_dt.strftime('%Y%m%dT%H%M%SZ') if start_dt.tzinfo else start_dt.strftime('%Y%m%dT%H%M%S')}
DTEND:{end_dt.strftime('%Y%m%dT%H%M%SZ') if end_dt.tzinfo else end_dt.strftime('%Y%m%dT%H%M%S')}
SUMMARY:{summary}
DESCRIPTION:Tracked via OrbitTrack
END:VEVENT
END:VCALENDAR"""

    calendar.save_event(vcal)
    return {"uid": event_uid, "summary": summary}


def list_events(
    url: str,
    username: str,
    password: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    """Return events from all calendars within a date range, grouped by calendar."""
    client = _connect(url, username, password)
    principal = client.principal()
    calendars = principal.calendars()

    if start_date:
        start_dt = datetime.fromisoformat(start_date)
    else:
        start_dt = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0) - timedelta(days=7)

    if end_date:
        end_dt = datetime.fromisoformat(end_date)
    else:
        end_dt = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59) + timedelta(days=7)

    grouped: list[dict[str, Any]] = []

    for cal in calendars:
        try:
            supported = cal.get_supported_components()
            if "VEVENT" not in supported:
                continue
        except Exception:
            pass

        try:
            events = cal.date_search(start=start_dt, end=end_dt, expand=True)
        except Exception:
            continue

        if not events:
            continue

        event_list = []
        for ev in events:
            try:
                vevent = ev.vobject_instance.vevent
                summary = str(vevent.summary.value) if hasattr(vevent, "summary") else "Untitled"
                uid = str(vevent.uid.value) if hasattr(vevent, "uid") else ""

                ev_start = None
                ev_end = None
                all_day = False

                if hasattr(vevent, "dtstart"):
                    val = vevent.dtstart.value
                    if isinstance(val, datetime):
                        ev_start = val.isoformat()
                    elif isinstance(val, date):
                        ev_start = val.isoformat()
                        all_day = True

                if hasattr(vevent, "dtend"):
                    val = vevent.dtend.value
                    if isinstance(val, datetime):
                        ev_end = val.isoformat()
                    elif isinstance(val, date):
                        ev_end = val.isoformat()

                if ev_start and not ev_end and hasattr(vevent, "duration"):
                    try:
                        dur = vevent.duration.value
                        start_val = vevent.dtstart.value
                        if isinstance(start_val, datetime):
                            ev_end = (start_val + dur).isoformat()
                    except Exception:
                        pass

                description = ""
                try:
                    if hasattr(vevent, "description"):
                        description = str(vevent.description.value)
                except Exception:
                    pass

                location = ""
                try:
                    if hasattr(vevent, "location"):
                        location = str(vevent.location.value)
                except Exception:
                    pass

                event_list.append({
                    "uid": uid,
                    "summary": summary,
                    "dtstart": ev_start,
                    "dtend": ev_end,
                    "all_day": all_day,
                    "description": description,
                    "location": location,
                    "calendar_id": str(cal.url),
                })
            except Exception:
                continue

        event_list.sort(key=lambda e: e.get("dtstart") or "")

        color = _get_calendar_color(cal)

        grouped.append({
            "calendar_id": str(cal.url),
            "calendar_name": cal.name or "Unnamed",
            "calendar_color": color,
            "events": event_list,
        })

    return grouped
