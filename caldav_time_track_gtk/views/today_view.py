"""TodayView – Shows today's calendar events."""

from __future__ import annotations

from datetime import datetime, timezone

import gi
gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, GLib, Gtk


class TodayView(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._build_ui()

    def set_loading(self, loading: bool) -> None:
        if loading:
            self._stack.set_visible_child_name("loading")

    def update(self, event_groups: list[dict]) -> None:
        # Clear old entries
        child = self._list_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._list_box.remove(child)
            child = nxt

        all_events = []
        for group in event_groups:
            for ev in group.get("events", []):
                ev = dict(ev)
                ev["_calendar_name"] = group["calendar_name"]
                ev["_calendar_color"] = group.get("calendar_color", "#4A90D9")
                all_events.append(ev)

        # Sort by start time
        all_events.sort(key=lambda e: e.get("dtstart") or "")

        if all_events:
            for ev in all_events:
                row = self._make_event_row(ev)
                self._list_box.append(row)
            self._stack.set_visible_child_name("content")
        else:
            self._stack.set_visible_child_name("empty")

    def _build_ui(self) -> None:
        # Date header
        today = datetime.now()
        header_label = Gtk.Label(
            label=today.strftime("Today, %A %B %-d")
        )
        header_label.add_css_class("title-3")
        header_label.set_margin_start(16)
        header_label.set_margin_end(16)
        header_label.set_margin_top(12)
        header_label.set_margin_bottom(8)
        header_label.set_halign(Gtk.Align.START)
        self.append(header_label)
        self.append(Gtk.Separator())

        self._stack = Gtk.Stack()

        # Loading
        loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        loading_box.set_valign(Gtk.Align.CENTER)
        loading_box.set_halign(Gtk.Align.CENTER)
        loading_box.set_vexpand(True)
        sp = Gtk.Spinner()
        sp.start()
        sp.set_size_request(32, 32)
        loading_box.append(sp)
        loading_box.append(Gtk.Label(label="Loading events…"))
        self._stack.add_named(loading_box, "loading")

        # Empty
        empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        empty_box.set_valign(Gtk.Align.CENTER)
        empty_box.set_halign(Gtk.Align.CENTER)
        empty_box.set_vexpand(True)
        icon = Gtk.Image.new_from_icon_name("x-office-calendar-symbolic")
        icon.set_pixel_size(64)
        icon.add_css_class("dim-label")
        empty_box.append(icon)
        lbl = Gtk.Label(label="No events today")
        lbl.add_css_class("title-2")
        lbl.add_css_class("dim-label")
        empty_box.append(lbl)
        self._stack.add_named(empty_box, "empty")

        # Content
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        self._list_box = Gtk.ListBox()
        self._list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._list_box.add_css_class("boxed-list")
        self._list_box.set_margin_start(12)
        self._list_box.set_margin_end(12)
        self._list_box.set_margin_top(8)
        self._list_box.set_margin_bottom(8)
        scroll.set_child(self._list_box)
        self._stack.add_named(scroll, "content")

        self._stack.set_visible_child_name("empty")
        self._stack.set_vexpand(True)
        self.append(self._stack)

    def _make_event_row(self, ev: dict) -> Adw.ActionRow:
        row = Adw.ActionRow()
        row.set_title(ev.get("summary", "Untitled"))

        # Time subtitle
        start_str = ev.get("dtstart", "")
        end_str = ev.get("dtend", "")
        parts = []
        if ev.get("all_day"):
            parts.append("All day")
        else:
            try:
                if start_str:
                    s = self._parse_dt(start_str)
                    parts.append(s.strftime("%H:%M"))
                if end_str:
                    e = self._parse_dt(end_str)
                    parts.append(e.strftime("%H:%M"))
            except Exception:
                pass
        time_str = " – ".join(parts)
        cal_str = ev.get("_calendar_name", "")
        subtitle = "  ·  ".join(filter(None, [time_str, cal_str]))
        if subtitle:
            row.set_subtitle(subtitle)

        if ev.get("description"):
            desc_btn = Gtk.Button.new_from_icon_name("view-more-symbolic")
            desc_btn.add_css_class("flat")
            desc_btn.add_css_class("circular")
            desc_btn.set_tooltip_text(ev["description"])
            row.add_suffix(desc_btn)

        return row

    @staticmethod
    def _parse_dt(s: str) -> datetime:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
