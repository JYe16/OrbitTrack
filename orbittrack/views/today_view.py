"""
TodayView – dashboard for the current day, matching the web app layout.

Cards
-----
1. Up Next         – next upcoming event (or "No upcoming events.")
2. Today's Tasks   – tasks due today (or "No tasks due today.")
3. Today's Events  – events grouped by calendar with colored dots
4. Time Analysis   – per‑calendar duration breakdown with percentages
"""

from __future__ import annotations

import math
from datetime import datetime, timezone, date as _date

import gi
gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, GLib, GObject, Gtk, Gdk


def _escape(text: str) -> str:
    return GLib.markup_escape_text(text)


def _parse_dt(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _fmt_time(dt: datetime) -> str:
    return dt.astimezone().strftime("%I:%M %p").lstrip("0")


def _fmt_duration(total_seconds: int) -> str:
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    parts = []
    if h:
        parts.append(f"{h}h")
    if m or not h:
        parts.append(f"{m:02d}m" if h else f"{m}m")
    return " ".join(parts)


def _event_sort_key(ev: dict) -> tuple:
    start_dt = ev.get("_start_dt")
    if isinstance(start_dt, datetime):
        return (0, start_dt.timestamp(), ev.get("summary", ""))
    return (1, float("inf"), ev.get("summary", ""))


class TodayView(Gtk.Box):
    """Full Today dashboard."""

    __gsignals__ = {
        "start-timer": (GObject.SignalFlags.RUN_FIRST, None, (str, str, str, str)),
    }

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._task_groups: list[dict] = []
        self._event_groups: list[dict] = []
        self._layout_narrow: bool | None = None
        self._root_width_handler_id: int = 0
        self._root_widget: Gtk.Widget | None = None
        self._build_ui()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_loading(self, loading: bool) -> None:
        if loading:
            self._stack.set_visible_child_name("loading")

    def update(self, event_groups: list[dict], task_groups: list[dict] | None = None) -> None:
        self._event_groups = event_groups or []
        if task_groups is not None:
            self._task_groups = task_groups or []
        self._rebuild()

    # ── Skeleton ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        today = datetime.now()
        header = Gtk.Label(label=today.strftime("Today, %A %B %-d"))
        header.add_css_class("title-3")
        header.set_halign(Gtk.Align.START)
        header.set_margin_start(16)
        header.set_margin_end(16)
        header.set_margin_top(12)
        header.set_margin_bottom(4)
        self.append(header)

        sub = Gtk.Label(label="Focus on what matters now.")
        sub.add_css_class("dim-label")
        sub.set_halign(Gtk.Align.START)
        sub.set_margin_start(16)
        sub.set_margin_bottom(8)
        self.append(sub)
        self.append(Gtk.Separator())

        self._stack = Gtk.Stack()

        load_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        load_box.set_valign(Gtk.Align.CENTER)
        load_box.set_halign(Gtk.Align.CENTER)
        load_box.set_vexpand(True)
        sp = Gtk.Spinner()
        sp.start()
        sp.set_size_request(32, 32)
        load_box.append(sp)
        load_box.append(Gtk.Label(label="Loading…"))
        self._stack.add_named(load_box, "loading")

        empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        empty_box.set_valign(Gtk.Align.CENTER)
        empty_box.set_halign(Gtk.Align.CENTER)
        empty_box.set_vexpand(True)
        icon = Gtk.Image.new_from_icon_name("x-office-calendar-symbolic")
        icon.set_pixel_size(64)
        icon.add_css_class("dim-label")
        empty_box.append(icon)
        lbl = Gtk.Label(label="Nothing for today")
        lbl.add_css_class("title-2")
        lbl.add_css_class("dim-label")
        empty_box.append(lbl)
        self._stack.add_named(empty_box, "empty")

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        clamp = Adw.Clamp()
        clamp.set_maximum_size(800)
        clamp.set_tightening_threshold(500)
        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._content.set_margin_start(12)
        self._content.set_margin_end(12)
        self._content.set_margin_top(12)
        self._content.set_margin_bottom(12)
        clamp.set_child(self._content)
        scroll.set_child(clamp)
        self._stack.add_named(scroll, "content")

        self._stack.set_visible_child_name("empty")
        self._stack.set_vexpand(True)
        self.append(self._stack)

        self.connect("notify::root", self._on_root_changed)
        self._on_root_changed(self, None)

    # ── Rebuild ───────────────────────────────────────────────────────────────

    def _rebuild(self) -> None:
        child = self._content.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._content.remove(child)
            child = nxt

        all_events = self._flatten_events()
        today_tasks = self._get_today_tasks()
        now = datetime.now(timezone.utc)

        upcoming = [
            e for e in all_events
            if not e.get("all_day") and e.get("_start_dt") and e["_start_dt"] > now
        ]
        upcoming.sort(key=lambda e: e["_start_dt"])

        if not all_events and not today_tasks:
            self._stack.set_visible_child_name("empty")
            return

        # 1–4: Responsive card grid (2 cols on wide, 1 col on narrow)
        narrow = self._is_narrow_layout()
        self._layout_narrow = narrow
        flowbox = Gtk.FlowBox()
        flowbox.set_homogeneous(False)
        flowbox.set_column_spacing(12)
        flowbox.set_row_spacing(12)
        flowbox.set_min_children_per_line(1)
        flowbox.set_max_children_per_line(1 if narrow else 2)
        flowbox.set_selection_mode(Gtk.SelectionMode.NONE)

        for card in (
            self._make_up_next_card(upcoming),
            self._make_todays_tasks_card(today_tasks),
            self._make_todays_events_card(all_events),
            self._make_time_analysis_card(all_events),
        ):
            card.set_hexpand(True)
            card.set_vexpand(False)
            flowbox.append(card)

        self._content.append(flowbox)
        self._stack.set_visible_child_name("content")

    def _on_root_changed(self, _widget: Gtk.Widget, _pspec) -> None:
        if self._root_widget and self._root_width_handler_id:
            self._root_widget.disconnect(self._root_width_handler_id)
            self._root_width_handler_id = 0

        root = self.get_root()
        self._root_widget = root if isinstance(root, Gtk.Widget) else None

        if self._root_widget:
            self._root_width_handler_id = self._root_widget.connect(
                "notify::width", self._on_root_width_changed
            )

        self._maybe_rebuild_for_layout_change()

    def _on_root_width_changed(self, _widget: Gtk.Widget, _pspec) -> None:
        self._maybe_rebuild_for_layout_change()

    def _maybe_rebuild_for_layout_change(self) -> None:
        narrow = self._is_narrow_layout()
        if self._layout_narrow is None:
            self._layout_narrow = narrow
            return
        if narrow != self._layout_narrow and self._event_groups is not None:
            self._rebuild()

    def _is_narrow_layout(self) -> bool:
        root = self.get_root()
        if isinstance(root, Gtk.Window):
            width = root.get_width()
            if width > 0:
                return width < 760

        width = self.get_width()
        if width > 0:
            return width < 760

        return False

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _flatten_events(self) -> list[dict]:
        result: list[dict] = []
        for group in self._event_groups:
            for ev in group.get("events", []):
                ev2 = dict(ev)
                ev2["_calendar_name"] = group.get("calendar_name", "")
                ev2["_calendar_color"] = group.get("calendar_color", "#4A90D9")
                try:
                    if ev2.get("dtstart"):
                        ev2["_start_dt"] = _parse_dt(ev2["dtstart"]).astimezone(timezone.utc)
                    if ev2.get("dtend"):
                        ev2["_end_dt"] = _parse_dt(ev2["dtend"]).astimezone(timezone.utc)
                except Exception:
                    pass
                result.append(ev2)
        result.sort(key=_event_sort_key)
        return result

    def _get_today_tasks(self) -> list[dict]:
        today_iso = _date.today().isoformat()
        result: list[dict] = []
        for group in self._task_groups:
            for task in group.get("tasks", []):
                due = task.get("due", "") or ""
                if due.startswith(today_iso):
                    t = dict(task)
                    t["_calendar_name"] = group.get("calendar_name", "")
                    t["_calendar_color"] = group.get("calendar_color", "#4A90D9")
                    result.append(t)
        return result

    def _collect_time_analysis(self, all_events: list[dict]) -> list[tuple[str, int, int, str]]:
        cal_durations: dict[str, dict] = {}
        for ev in all_events:
            if ev.get("all_day"):
                continue
            start = ev.get("_start_dt")
            end = ev.get("_end_dt")
            if not start or not end:
                continue
            dur = int((end - start).total_seconds())
            if dur <= 0:
                continue
            cal_name = ev.get("_calendar_name") or "Other"
            cal_color = ev.get("_calendar_color", "#4A90D9")
            if cal_name not in cal_durations:
                cal_durations[cal_name] = {"secs": 0, "color": cal_color}
            cal_durations[cal_name]["secs"] += dur

        total_secs = sum(v["secs"] for v in cal_durations.values())
        result: list[tuple[str, int, int, str]] = []
        for name, info in sorted(cal_durations.items(), key=lambda x: -x[1]["secs"]):
            pct = round(info["secs"] / total_secs * 100) if total_secs else 0
            result.append((name, info["secs"], pct, info["color"]))
        return result

    # ── Card 2: Up Next ───────────────────────────────────────────────────────

    def _make_up_next_card(self, upcoming: list[dict]) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.add_css_class("card")
        card.set_vexpand(True)

        title = Gtk.Label(label="Up Next")
        title.add_css_class("heading")
        title.set_halign(Gtk.Align.START)
        title.set_margin_start(12)
        title.set_margin_top(10)
        title.set_margin_bottom(6)
        card.append(title)

        if upcoming:
            ev = upcoming[0]
            row = Adw.ActionRow()
            row.set_title(_escape(ev.get("summary", "Untitled")))
            parts = []
            if ev.get("_start_dt"):
                parts.append(_fmt_time(ev["_start_dt"]))
            if ev.get("_end_dt"):
                parts.append(_fmt_time(ev["_end_dt"]))
            if parts:
                row.set_subtitle(_escape(" – ".join(parts)))
            card.append(row)
        else:
            empty = Gtk.Label(label="No upcoming events.")
            empty.add_css_class("dim-label")
            empty.set_margin_start(12)
            empty.set_margin_top(4)
            empty.set_margin_bottom(12)
            empty.set_halign(Gtk.Align.START)
            card.append(empty)
        return card

    # ── Card 2: Today's Tasks ─────────────────────────────────────────────────

    def _make_todays_tasks_card(self, tasks: list[dict]) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.add_css_class("card")
        card.set_vexpand(True)

        title = Gtk.Label(label="Today's Tasks")
        title.add_css_class("heading")
        title.set_halign(Gtk.Align.START)
        title.set_margin_start(12)
        title.set_margin_top(10)
        title.set_margin_bottom(6)
        card.append(title)

        if not tasks:
            empty = Gtk.Label(label="No tasks due today.")
            empty.add_css_class("dim-label")
            empty.set_halign(Gtk.Align.START)
            empty.set_margin_start(12)
            empty.set_margin_top(4)
            empty.set_margin_bottom(12)
            card.append(empty)
            return card

        lb = Gtk.ListBox()
        lb.set_selection_mode(Gtk.SelectionMode.NONE)
        lb.add_css_class("boxed-list")
        for task in tasks:
            row = Adw.ActionRow()
            row.set_title(_escape(task.get("summary", "Untitled")))
            sub_parts = []
            if task.get("_calendar_name"):
                sub_parts.append(task["_calendar_name"])
            if task.get("priority") and task["priority"] > 0:
                if task["priority"] <= 3:
                    sub_parts.append("High priority")
                elif task["priority"] <= 6:
                    sub_parts.append("Medium priority")
            if sub_parts:
                row.set_subtitle(_escape(" · ".join(sub_parts)))
            check = Gtk.CheckButton()
            check.set_active(task.get("status") == "COMPLETED")
            check.set_valign(Gtk.Align.CENTER)
            row.add_prefix(check)
            lb.append(row)
        card.append(lb)
        return card

    # ── Card 3: Today's Events ────────────────────────────────────────────────

    def _make_todays_events_card(self, all_events: list[dict]) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.add_css_class("card")
        card.set_vexpand(True)

        title = Gtk.Label(label="Today's Events")
        title.add_css_class("heading")
        title.set_halign(Gtk.Align.START)
        title.set_margin_start(12)
        title.set_margin_top(10)
        title.set_margin_bottom(6)
        card.append(title)

        has_any = False
        if all_events:
            has_any = True
            lb = Gtk.ListBox()
            lb.set_selection_mode(Gtk.SelectionMode.NONE)
            lb.add_css_class("boxed-list")
            lb.set_margin_start(4)
            lb.set_margin_end(4)
            lb.set_margin_bottom(4)

            for ev in all_events:
                row = Adw.ActionRow()
                dot = Gtk.DrawingArea()
                dot.set_size_request(12, 12)
                dot.set_draw_func(_make_dot_draw(ev.get("_calendar_color", "#4A90D9")))
                dot.set_valign(Gtk.Align.CENTER)
                row.add_prefix(dot)
                row.set_title(_escape(ev.get("summary", "Untitled")))
                parts = []
                if ev.get("all_day"):
                    parts.append("All day")
                else:
                    try:
                        if ev.get("_start_dt"):
                            parts.append(_fmt_time(ev["_start_dt"]))
                        if ev.get("_end_dt"):
                            parts.append(_fmt_time(ev["_end_dt"]))
                    except Exception:
                        pass
                if parts:
                    row.set_subtitle(_escape(" – ".join(parts)))
                lb.append(row)
            card.append(lb)

        if not has_any:
            empty = Gtk.Label(label="No events today.")
            empty.add_css_class("dim-label")
            empty.set_halign(Gtk.Align.START)
            empty.set_margin_start(12)
            empty.set_margin_top(4)
            empty.set_margin_bottom(12)
            card.append(empty)
        return card

    # ── Card 4: Time Analysis ─────────────────────────────────────────────────

    def _make_time_analysis_card(self, all_events: list[dict]) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.add_css_class("card")

        title = Gtk.Label(label="Time Analysis")
        title.add_css_class("heading")
        title.set_halign(Gtk.Align.START)
        title.set_margin_start(12)
        title.set_margin_top(10)
        title.set_margin_bottom(6)
        card.append(title)

        analysis = self._collect_time_analysis(all_events)
        if not analysis:
            empty = Gtk.Label(label="No timed events.")
            empty.add_css_class("dim-label")
            empty.set_halign(Gtk.Align.START)
            empty.set_margin_start(12)
            empty.set_margin_top(4)
            empty.set_margin_bottom(12)
            card.append(empty)
            return card

        lb = Gtk.ListBox()
        lb.set_selection_mode(Gtk.SelectionMode.NONE)
        lb.add_css_class("boxed-list")
        lb.set_margin_start(4)
        lb.set_margin_end(4)
        lb.set_margin_bottom(4)

        for name, secs, pct, color in analysis:
            row = Adw.ActionRow()
            dot = Gtk.DrawingArea()
            dot.set_size_request(12, 12)
            dot.set_draw_func(_make_dot_draw(color))
            dot.set_valign(Gtk.Align.CENTER)
            row.add_prefix(dot)
            row.set_title(_escape(name))
            row.set_subtitle(_fmt_duration(secs))
            pct_label = Gtk.Label(label=f"{pct}%")
            pct_label.add_css_class("dim-label")
            row.add_suffix(pct_label)
            lb.append(row)

        card.append(lb)
        return card


# ── Module-level helper ──────────────────────────────────────────────────────

def _make_dot_draw(color_hex: str):
    def draw_func(_area, cr, w, h):
        try:
            rgba = Gdk.RGBA()
            rgba.parse(color_hex)
            cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
        except Exception:
            cr.set_source_rgb(0.29, 0.56, 0.85)
        r = min(w, h) / 2
        cr.arc(w / 2, h / 2, r, 0, 2 * math.pi)
        cr.fill()
    return draw_func
