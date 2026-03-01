"""
MainWindow – top-level application window (GTK4 / Libadwaita).

Layout
------
Adw.ApplicationWindow
  Gtk.Overlay                          ← lets the timer slide on top
    Gtk.Stack  (page_stack)
      "login"  → LoginView
      "main"   → Adw.ToolbarView
                   HeaderBar  (ViewSwitcher centred + action buttons)
                   Adw.ViewStack
                     tasks    → TasksView
                     today    → TodayView
                     calendar → CalendarView
                   ViewSwitcherBar  (bottom, responsive)
    TimerOverlay                       ← GTK overlay child, hidden by default
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

import gi
gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, GLib, Gtk

from .. import caldav_service, config
from ..views.login_view import LoginView
from ..views.tasks_view import TasksView
from ..views.today_view import TodayView
from ..views.calendar_view import CalendarView
from ..views.timer_overlay import TimerOverlay


class MainWindow(Adw.ApplicationWindow):
    # ── ctor ──────────────────────────────────────────────────────────────────

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title("CalDAV Time Track")
        self.set_default_size(900, 680)

        # Shared state
        self._creds: dict | None = None          # {url, username, password}
        self._settings: dict = config.load_settings()
        self._calendars: list[dict] = []
        self._task_groups: list[dict] = []

        # Active timer state
        self._active_timer: dict | None = None   # see _start_timer()
        self._timer_tick_id: int = 0             # GLib source id

        self._build_ui()

        # Try auto-login from saved credentials
        saved = config.load_credentials()
        if saved:
            self._login_view.prefill(saved["url"], saved["username"], saved["password"])
            self._do_login(saved["url"], saved["username"], saved["password"], remember=True)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Outer overlay (timer floats above everything)
        self._overlay = Gtk.Overlay()

        # Page stack: login ↔ main
        self._page_stack = Gtk.Stack()
        self._page_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._page_stack.set_transition_duration(200)

        # ── Login page ──
        self._login_view = LoginView()
        self._login_view.connect("login-requested", self._on_login_requested)
        self._page_stack.add_named(self._login_view, "login")

        # ── Main page ──
        main_page = self._build_main_page()
        self._page_stack.add_named(main_page, "main")

        # Timer overlay widget
        self._timer_overlay = TimerOverlay()
        self._timer_overlay.connect("timer-stopped", self._on_timer_stopped)
        self._timer_overlay.set_visible(False)
        self._timer_overlay.set_halign(Gtk.Align.FILL)
        self._timer_overlay.set_valign(Gtk.Align.FILL)

        self._overlay.set_child(self._page_stack)
        self._overlay.add_overlay(self._timer_overlay)

        self.set_content(self._overlay)

        self._page_stack.set_visible_child_name("login")

    def _build_main_page(self) -> Gtk.Widget:
        # ViewStack (content tabs)
        self._view_stack = Adw.ViewStack()

        self._tasks_view = TasksView()
        self._tasks_view.connect("start-timer", self._on_start_timer)
        self._tasks_view.connect("task-changed", self._on_task_changed)

        self._today_view = TodayView()
        self._calendar_view = CalendarView()

        self._view_stack.add_titled_with_icon(
            self._tasks_view, "tasks", "Tasks", "checkbox-checked-symbolic"
        )
        self._view_stack.add_titled_with_icon(
            self._today_view, "today", "Today", "x-office-calendar-symbolic"
        )
        self._view_stack.add_titled_with_icon(
            self._calendar_view, "calendar", "Calendar", "month-symbolic"
        )

        # ViewSwitcher for header (wide screens)
        switcher = Adw.ViewSwitcher()
        switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        switcher.set_stack(self._view_stack)

        # HeaderBar
        header = Adw.HeaderBar()
        header.set_title_widget(switcher)

        # Refresh button
        refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Refresh")
        refresh_btn.connect("clicked", self._on_refresh_clicked)
        self._refresh_btn = refresh_btn

        # Settings button
        settings_btn = Gtk.Button.new_from_icon_name("emblem-system-symbolic")
        settings_btn.set_tooltip_text("Settings")
        settings_btn.connect("clicked", self._on_settings_clicked)

        # Logout button
        logout_btn = Gtk.Button.new_from_icon_name("system-log-out-symbolic")
        logout_btn.set_tooltip_text("Logout")
        logout_btn.connect("clicked", self._on_logout_clicked)

        header.pack_end(logout_btn)
        header.pack_end(settings_btn)
        header.pack_end(refresh_btn)

        # ViewSwitcherBar (bottom, narrow screens)
        switcher_bar = Adw.ViewSwitcherBar()
        switcher_bar.set_stack(self._view_stack)

        # Reveal bottom bar only when header switcher overflows
        switcher_bar.set_reveal(True)

        # ToolbarView wraps everything
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        toolbar_view.set_content(self._view_stack)
        toolbar_view.add_bottom_bar(switcher_bar)

        return toolbar_view

    # ── Login flow ────────────────────────────────────────────────────────────

    def _on_login_requested(
        self,
        _view: LoginView,
        url: str,
        username: str,
        password: str,
        remember: bool,
    ) -> None:
        self._login_view.set_sensitive(False)
        self._login_view.set_loading(True)
        self._do_login(url, username, password, remember)

    def _do_login(
        self, url: str, username: str, password: str, remember: bool = False
    ) -> None:
        def _worker():
            try:
                ok = caldav_service.verify_credentials(url, username, password)
            except Exception:
                ok = False
            GLib.idle_add(self._finish_login, ok, url, username, password, remember)

        threading.Thread(target=_worker, daemon=True).start()

    def _finish_login(
        self,
        ok: bool,
        url: str,
        username: str,
        password: str,
        remember: bool,
    ) -> None:
        self._login_view.set_sensitive(True)
        self._login_view.set_loading(False)
        if ok:
            self._creds = {"url": url, "username": username, "password": password}
            if remember:
                config.save_credentials(url, username, password)
            # Propagate credentials to views that perform network ops
            self._tasks_view.set_credentials(self._creds)
            self._page_stack.set_visible_child_name("main")
            self._refresh_all()
        else:
            self._login_view.show_error("Could not connect – check URL and credentials.")

    # ── Refresh ───────────────────────────────────────────────────────────────

    def _on_refresh_clicked(self, _btn: Gtk.Button) -> None:
        self._refresh_all()

    def _refresh_all(self) -> None:
        if not self._creds:
            return
        self._refresh_btn.set_sensitive(False)
        self._tasks_view.set_loading(True)
        self._today_view.set_loading(True)
        self._calendar_view.set_loading(True)

        creds = self._creds
        show_completed = self._settings.get("show_completed", False)

        def _worker():
            try:
                cals = caldav_service.list_calendars(**creds)
            except Exception:
                cals = []
            try:
                task_groups = caldav_service.list_tasks(
                    **creds, show_completed=show_completed
                )
            except Exception:
                task_groups = []

            now = datetime.now(timezone.utc)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            today_end = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()
            week_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = (week_start.replace(day=week_start.day - week_start.weekday())).isoformat()
            week_end_dt = datetime.fromisoformat(week_start).replace(
                hour=23, minute=59, second=59
            )
            from datetime import timedelta
            week_end = (week_end_dt + timedelta(days=6)).isoformat()

            try:
                today_events = caldav_service.list_events(
                    **creds, start_date=today_start, end_date=today_end
                )
            except Exception:
                today_events = []
            try:
                week_events = caldav_service.list_events(
                    **creds, start_date=week_start, end_date=week_end
                )
            except Exception:
                week_events = []

            GLib.idle_add(
                self._finish_refresh,
                cals,
                task_groups,
                today_events,
                week_events,
            )

        threading.Thread(target=_worker, daemon=True).start()

    def _finish_refresh(
        self,
        calendars: list,
        task_groups: list,
        today_events: list,
        week_events: list,
    ) -> None:
        self._calendars = calendars
        self._task_groups = task_groups

        self._tasks_view.set_calendars(calendars)
        self._tasks_view.update(task_groups)
        self._today_view.update(today_events)
        self._calendar_view.update(week_events)

        self._tasks_view.set_loading(False)
        self._today_view.set_loading(False)
        self._calendar_view.set_loading(False)
        self._refresh_btn.set_sensitive(True)

    def _on_task_changed(self, _view, *_args) -> None:
        """A task was created/updated/deleted – refresh task list silently."""
        if not self._creds:
            return
        creds = self._creds
        show_completed = self._settings.get("show_completed", False)

        def _worker():
            try:
                task_groups = caldav_service.list_tasks(**creds, show_completed=show_completed)
            except Exception:
                task_groups = self._task_groups
            GLib.idle_add(self._tasks_view.update, task_groups)

        threading.Thread(target=_worker, daemon=True).start()

    # ── Timer ─────────────────────────────────────────────────────────────────

    def _on_start_timer(
        self,
        _view: TasksView,
        mode: str,         # "stopwatch" | "pomodoro"
        task_uid: str,
        summary: str,
        calendar_id: str,
    ) -> None:
        if self._active_timer:
            return  # already running

        pomodoro_secs = self._settings.get("pomodoro_duration", 25) * 60

        self._active_timer = {
            "mode": mode,
            "task_uid": task_uid,
            "summary": summary,
            "calendar_id": calendar_id,
            "started_at": datetime.now(timezone.utc),
            "elapsed_secs": 0,
            "phase": "work",          # for pomodoro: "work" | "break"
            "round": 1,
            "pomodoro_secs": pomodoro_secs,
        }

        self._timer_overlay.start(self._active_timer)
        self._timer_overlay.set_visible(True)

        self._timer_tick_id = GLib.timeout_add(1000, self._timer_tick)

    def _timer_tick(self) -> bool:
        if not self._active_timer:
            return False

        self._active_timer["elapsed_secs"] += 1
        self._timer_overlay.tick(self._active_timer)

        if self._active_timer["mode"] == "pomodoro":
            pom_secs = self._active_timer["pomodoro_secs"]
            elapsed = self._active_timer["elapsed_secs"]
            phase = self._active_timer["phase"]

            if phase == "work" and elapsed >= pom_secs:
                # Work period done – switch to break
                self._active_timer["elapsed_secs"] = 0
                self._active_timer["phase"] = "break"
                self._timer_overlay.tick(self._active_timer)
                self._save_timer_event(self._active_timer, pom_secs)
            elif phase == "break" and elapsed >= 5 * 60:
                # Break done – new round
                self._active_timer["elapsed_secs"] = 0
                self._active_timer["phase"] = "work"
                self._active_timer["round"] += 1
                self._timer_overlay.tick(self._active_timer)

        return True  # keep ticking

    def _on_timer_stopped(self, _overlay: TimerOverlay) -> None:
        if not self._active_timer:
            return

        if self._timer_tick_id:
            GLib.source_remove(self._timer_tick_id)
            self._timer_tick_id = 0

        timer = self._active_timer
        self._active_timer = None
        self._timer_overlay.set_visible(False)

        elapsed = timer["elapsed_secs"]
        if elapsed < 30:
            return  # too short, don't save event

        target_cal = self._settings.get("target_calendar_id") or timer["calendar_id"]
        self._save_timer_event(timer, elapsed, target_cal)

    def _save_timer_event(
        self, timer: dict, duration_secs: int, calendar_id: str | None = None
    ) -> None:
        if not self._creds:
            return

        cal_id = calendar_id or timer.get("calendar_id", "")
        if not cal_id:
            # Pick first event-capable calendar
            for cal in self._calendars:
                if cal.get("supports_events", True):
                    cal_id = cal["id"]
                    break
        if not cal_id:
            return

        end_dt = datetime.now(timezone.utc)
        from datetime import timedelta
        start_dt = end_dt - timedelta(seconds=duration_secs)
        summary = timer["summary"]

        creds = self._creds

        def _worker():
            try:
                caldav_service.create_event(
                    **creds,
                    calendar_id=cal_id,
                    summary=summary,
                    dtstart=start_dt.isoformat(),
                    dtend=end_dt.isoformat(),
                )
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    # ── Settings ─────────────────────────────────────────────────────────────

    def _on_settings_clicked(self, _btn: Gtk.Button) -> None:
        dlg = _SettingsDialog(
            parent=self,
            settings=self._settings,
            calendars=self._calendars,
        )
        dlg.connect("settings-saved", self._on_settings_saved)
        dlg.present()

    def _on_settings_saved(self, _dlg, settings: dict) -> None:
        self._settings = settings
        config.save_settings(settings)
        # Re-fetch with new show_completed preference
        self._on_task_changed(None)

    # ── Logout ────────────────────────────────────────────────────────────────

    def _on_logout_clicked(self, _btn: Gtk.Button) -> None:
        config.clear_credentials()
        self._creds = None
        self._task_groups = []
        self._calendars = []
        self._tasks_view.update([])
        self._today_view.update([])
        self._calendar_view.update([])
        self._page_stack.set_visible_child_name("login")


# ── Settings dialog ───────────────────────────────────────────────────────────


class _SettingsDialog(Adw.Dialog):
    __gsignals__ = {
        "settings-saved": (
            GLib.SignalFlags.RUN_FIRST,
            None,
            (object,),
        )
    }

    def __init__(self, parent: Gtk.Window, settings: dict, calendars: list):
        super().__init__()
        self.set_title("Settings")
        self.set_content_width(420)

        self._settings = dict(settings)
        self._calendars = calendars

        # Use a ToolbarView with HeaderBar so the dialog looks native on GNOME 49
        toolbar_view = Adw.ToolbarView()

        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: self.close())
        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save)
        header.pack_start(cancel_btn)
        header.pack_end(save_btn)
        toolbar_view.add_top_bar(header)

        prefs_page = Adw.PreferencesPage()

        # ── Calendar group ──
        cal_group = Adw.PreferencesGroup(title="Time Entries")
        cal_group.set_description("Where tracked time sessions are saved")

        event_cals = [c for c in calendars if c.get("supports_events", True)]
        # Build string list: first item is "Auto"
        cal_names = ["— Auto —"] + [c["name"] for c in event_cals]
        self._event_cals = event_cals  # keep ref for _on_save

        self._cal_row = Adw.ComboRow(title="Target calendar")
        str_list = Gtk.StringList.new(cal_names)
        self._cal_row.set_model(str_list)
        active_id = settings.get("target_calendar_id", "")
        sel_idx = 0
        for i, c in enumerate(event_cals):
            if c["id"] == active_id:
                sel_idx = i + 1
                break
        self._cal_row.set_selected(sel_idx)
        cal_group.add(self._cal_row)
        prefs_page.add(cal_group)

        # ── Timer group ──
        timer_group = Adw.PreferencesGroup(title="Timer")

        # Adw.SpinRow requires libadwaita 1.6 (GNOME 47+, available in GNOME 49)
        self._pom_row = Adw.SpinRow.new_with_range(1, 120, 1)
        self._pom_row.set_title("Pomodoro duration")
        self._pom_row.set_subtitle("Minutes per work session")
        self._pom_row.set_value(settings.get("pomodoro_duration", 25))
        timer_group.add(self._pom_row)
        prefs_page.add(timer_group)

        # ── Tasks group ──
        tasks_group = Adw.PreferencesGroup(title="Tasks")

        # Adw.SwitchRow requires libadwaita 1.4
        self._show_row = Adw.SwitchRow(title="Show completed tasks")
        self._show_row.set_active(settings.get("show_completed", False))
        tasks_group.add(self._show_row)
        prefs_page.add(tasks_group)

        toolbar_view.set_content(prefs_page)
        self.set_child(toolbar_view)

    def _on_save(self, _btn: Gtk.Button) -> None:
        sel = self._cal_row.get_selected()
        if sel == 0 or sel >= len(self._event_cals) + 1:
            cal_id = ""
        else:
            cal_id = self._event_cals[sel - 1]["id"]
        self._settings["target_calendar_id"] = cal_id
        self._settings["pomodoro_duration"] = int(self._pom_row.get_value())
        self._settings["show_completed"] = self._show_row.get_active()
        self.emit("settings-saved", self._settings)
        self.close()
