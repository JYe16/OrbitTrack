"""CalendarView – Weekly calendar grid showing events."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, date

import gi
gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, GLib, Gtk


class CalendarView(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._event_groups: list[dict] = []
        # Week offset from today (0 = current week)
        self._week_offset = 0
        self._build_ui()

    def set_loading(self, loading: bool) -> None:
        if loading:
            self._stack.set_visible_child_name("loading")

    def update(self, event_groups: list[dict]) -> None:
        self._event_groups = event_groups
        self._rebuild_calendar()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Navigation bar
        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        nav.set_margin_start(12)
        nav.set_margin_end(12)
        nav.set_margin_top(8)
        nav.set_margin_bottom(8)

        prev_btn = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        prev_btn.add_css_class("flat")
        prev_btn.connect("clicked", self._on_prev_week)
        nav.append(prev_btn)

        self._week_label = Gtk.Label()
        self._week_label.set_hexpand(True)
        self._week_label.add_css_class("title-4")
        nav.append(self._week_label)

        today_btn = Gtk.Button(label="Today")
        today_btn.add_css_class("flat")
        today_btn.connect("clicked", self._on_go_today)
        nav.append(today_btn)

        next_btn = Gtk.Button.new_from_icon_name("go-next-symbolic")
        next_btn.add_css_class("flat")
        next_btn.connect("clicked", self._on_next_week)
        nav.append(next_btn)

        self.append(nav)
        self.append(Gtk.Separator())

        # Day headers
        day_header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        day_header_box.set_homogeneous(True)
        self._day_headers: list[Gtk.Label] = []
        for _ in range(7):
            lbl = Gtk.Label()
            lbl.add_css_class("caption")
            lbl.add_css_class("dim-label")
            lbl.set_margin_start(4)
            lbl.set_margin_top(4)
            lbl.set_margin_bottom(4)
            lbl.set_halign(Gtk.Align.CENTER)
            day_header_box.append(lbl)
            self._day_headers.append(lbl)

        self.append(day_header_box)
        self.append(Gtk.Separator())

        # Stack: loading | content
        self._stack = Gtk.Stack()

        loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        loading_box.set_valign(Gtk.Align.CENTER)
        loading_box.set_halign(Gtk.Align.CENTER)
        loading_box.set_vexpand(True)
        sp = Gtk.Spinner()
        sp.start()
        sp.set_size_request(32, 32)
        loading_box.append(sp)
        loading_box.append(Gtk.Label(label="Loading calendar…"))
        self._stack.add_named(loading_box, "loading")

        # Content: scrollable day columns
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        self._day_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self._day_box.set_homogeneous(True)
        self._day_box.set_vexpand(True)
        self._day_columns: list[Gtk.Box] = []
        for _ in range(7):
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            col.set_margin_start(4)
            col.set_margin_end(4)
            col.set_margin_top(4)
            col.set_margin_bottom(4)
            col.set_valign(Gtk.Align.START)
            self._day_box.append(col)
            self._day_columns.append(col)

        scroll.set_child(self._day_box)
        self._stack.add_named(scroll, "content")

        self._stack.set_visible_child_name("content")
        self._stack.set_vexpand(True)
        self.append(self._stack)

        self._update_week_header()

    # ── Navigation ────────────────────────────────────────────────────────────

    def _on_prev_week(self, _btn) -> None:
        self._week_offset -= 1
        self._update_week_header()
        self._rebuild_calendar()

    def _on_next_week(self, _btn) -> None:
        self._week_offset += 1
        self._update_week_header()
        self._rebuild_calendar()

    def _on_go_today(self, _btn) -> None:
        self._week_offset = 0
        self._update_week_header()
        self._rebuild_calendar()

    def _week_start(self) -> date:
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        return monday + timedelta(weeks=self._week_offset)

    def _update_week_header(self) -> None:
        ws = self._week_start()
        we = ws + timedelta(days=6)
        if ws.month == we.month:
            self._week_label.set_text(f"{ws.strftime('%B %-d')} – {we.day}, {we.year}")
        else:
            self._week_label.set_text(f"{ws.strftime('%b %-d')} – {we.strftime('%b %-d')}, {we.year}")

        today = date.today()
        for i, lbl in enumerate(self._day_headers):
            d = ws + timedelta(days=i)
            text = d.strftime("%a %-d")
            lbl.set_text(text)
            if d == today:
                lbl.remove_css_class("dim-label")
                lbl.add_css_class("accent")
            else:
                lbl.remove_css_class("accent")
                lbl.add_css_class("dim-label")

    def _rebuild_calendar(self) -> None:
        ws = self._week_start()

        # Build day → events mapping
        day_events: dict[date, list[dict]] = {ws + timedelta(days=i): [] for i in range(7)}

        for group in self._event_groups:
            cal_name = group.get("calendar_name", "")
            for ev in group.get("events", []):
                try:
                    dtstart_str = ev.get("dtstart", "")
                    if not dtstart_str:
                        continue
                    if ev.get("all_day"):
                        d = date.fromisoformat(dtstart_str[:10])
                    else:
                        if dtstart_str.endswith("Z"):
                            dtstart_str = dtstart_str[:-1] + "+00:00"
                        dt = datetime.fromisoformat(dtstart_str)
                        d = dt.astimezone().date()

                    if d in day_events:
                        ev2 = dict(ev)
                        ev2["_calendar_name"] = cal_name
                        ev2["_calendar_color"] = group.get("calendar_color", "#4A90D9")
                        day_events[d].append(ev2)
                except Exception:
                    continue

        today = date.today()
        for i, col in enumerate(self._day_columns):
            # Clear column
            child = col.get_first_child()
            while child:
                nxt = child.get_next_sibling()
                col.remove(child)
                child = nxt

            d = ws + timedelta(days=i)
            evs = day_events.get(d, [])
            evs.sort(key=lambda e: e.get("dtstart") or "")

            if d == today:
                col.add_css_class("today-col")
            else:
                col.remove_css_class("today-col")

            for ev in evs:
                chip = self._make_event_chip(ev)
                col.append(chip)

        self._stack.set_visible_child_name("content")

    def _make_event_chip(self, ev: dict) -> Gtk.Button:
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vbox.set_margin_start(2)
        vbox.set_margin_end(2)
        vbox.set_margin_top(2)
        vbox.set_margin_bottom(2)

        summary_lbl = Gtk.Label(label=ev.get("summary", ""))
        summary_lbl.add_css_class("caption")
        summary_lbl.set_ellipsize(3)  # PANGO_ELLIPSIZE_END = 3
        summary_lbl.set_halign(Gtk.Align.START)
        vbox.append(summary_lbl)

        if not ev.get("all_day"):
            try:
                dtstart_str = ev.get("dtstart", "")
                if dtstart_str.endswith("Z"):
                    dtstart_str = dtstart_str[:-1] + "+00:00"
                dt = datetime.fromisoformat(dtstart_str)
                time_lbl = Gtk.Label(label=dt.astimezone().strftime("%H:%M"))
                time_lbl.add_css_class("caption")
                time_lbl.add_css_class("dim-label")
                time_lbl.set_halign(Gtk.Align.START)
                vbox.append(time_lbl)
            except Exception:
                pass

        btn = Gtk.Button()
        btn.set_child(vbox)
        btn.add_css_class("flat")
        btn.add_css_class("event-chip")
        btn.set_tooltip_text(ev.get("summary", ""))
        btn.set_halign(Gtk.Align.FILL)
        return btn
