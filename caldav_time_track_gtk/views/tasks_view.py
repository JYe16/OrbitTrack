"""
TasksView – Displays CalDAV tasks grouped by calendar.

Signals emitted
---------------
start-timer(mode, task_uid, summary, calendar_id)
task-changed()
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

import gi
gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, GLib, Gtk, Gdk

from .. import caldav_service


class TasksView(Gtk.Box):
    __gsignals__ = {
        "start-timer": (GLib.SignalFlags.RUN_FIRST, None, (str, str, str, str)),
        "task-changed": (GLib.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._creds: dict | None = None
        self._groups: list[dict] = []
        self._calendars: list[dict] = []
        self._build_ui()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_credentials(self, creds: dict | None) -> None:
        self._creds = creds

    def set_calendars(self, calendars: list[dict]) -> None:
        self._calendars = calendars

    def set_loading(self, loading: bool) -> None:
        if loading:
            self._status_stack.set_visible_child_name("loading")
            self._content_scroll.set_visible(False)
        # loading=False is handled in update()

    def update(self, task_groups: list[dict]) -> None:
        self._groups = task_groups
        self._rebuild_list()
        if task_groups:
            self._status_stack.set_visible_child_name("empty")  # hidden
            self._content_scroll.set_visible(True)
            total = sum(len(g["tasks"]) for g in task_groups)
            if total == 0:
                self._status_stack.set_visible_child_name("no_tasks")
                self._content_scroll.set_visible(False)
        else:
            self._status_stack.set_visible_child_name("no_tasks")
            self._content_scroll.set_visible(False)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Toolbar with "New Task" button
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_margin_start(12)
        toolbar.set_margin_end(12)
        toolbar.set_margin_top(8)
        toolbar.set_margin_bottom(8)

        new_btn = Gtk.Button(label="New Task")
        new_btn.add_css_class("suggested-action")
        new_btn.add_css_class("pill")
        new_btn.set_icon_name("list-add-symbolic")
        new_btn.connect("clicked", self._on_new_task_clicked)
        toolbar.append(new_btn)

        self.append(toolbar)
        self.append(Gtk.Separator())

        # Status stack (loading / no tasks)
        self._status_stack = Gtk.Stack()

        loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        loading_box.set_valign(Gtk.Align.CENTER)
        loading_box.set_halign(Gtk.Align.CENTER)
        loading_box.set_vexpand(True)
        spinner = Gtk.Spinner()
        spinner.start()
        spinner.set_size_request(32, 32)
        loading_box.append(spinner)
        loading_box.append(Gtk.Label(label="Loading tasks…"))

        no_tasks_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        no_tasks_box.set_valign(Gtk.Align.CENTER)
        no_tasks_box.set_halign(Gtk.Align.CENTER)
        no_tasks_box.set_vexpand(True)
        icon = Gtk.Image.new_from_icon_name("checkbox-checked-symbolic")
        icon.set_pixel_size(64)
        icon.add_css_class("dim-label")
        no_tasks_box.append(icon)
        no_tasks_label = Gtk.Label(label="No tasks")
        no_tasks_label.add_css_class("title-2")
        no_tasks_label.add_css_class("dim-label")
        no_tasks_box.append(no_tasks_label)

        self._status_stack.add_named(loading_box, "loading")
        self._status_stack.add_named(no_tasks_box, "no_tasks")
        self._status_stack.set_visible_child_name("no_tasks")
        self._status_stack.set_vexpand(True)

        self.append(self._status_stack)

        # Scrollable task content
        self._content_scroll = Gtk.ScrolledWindow()
        self._content_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._content_scroll.set_vexpand(True)
        self._content_scroll.set_visible(False)

        self._content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._content_scroll.set_child(self._content_box)

        self.append(self._content_scroll)

    def _rebuild_list(self) -> None:
        # Remove old children
        child = self._content_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._content_box.remove(child)
            child = nxt

        for group in self._groups:
            if not group["tasks"]:
                continue
            section = _TaskGroupWidget(group, self)
            self._content_box.append(section)

    # ── Callbacks from task rows ───────────────────────────────────────────────

    def on_start_timer(self, mode: str, task: dict) -> None:
        self.emit(
            "start-timer",
            mode,
            task["uid"],
            task["summary"],
            task["calendar_id"],
        )

    def on_toggle_complete(self, task: dict) -> None:
        if not self._creds:
            return
        new_status = "NEEDS-ACTION" if task["status"] == "COMPLETED" else "COMPLETED"
        creds = self._creds

        def _worker():
            try:
                caldav_service.update_task(
                    **creds,
                    calendar_id=task["calendar_id"],
                    task_uid=task["uid"],
                    status=new_status,
                )
            except Exception:
                pass
            GLib.idle_add(self.emit, "task-changed")

        threading.Thread(target=_worker, daemon=True).start()

    def on_delete_task(self, task: dict, parent_widget: Gtk.Widget) -> None:
        if not self._creds:
            return

        dlg = Adw.AlertDialog(
            heading="Delete task?",
            body=f"'{task['summary']}' will be permanently deleted.",
        )
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("delete", "Delete")
        dlg.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")

        def _on_response(d, response):
            if response == "delete":
                self._do_delete_task(task)

        dlg.connect("response", _on_response)
        dlg.present(self.get_root())

    def _do_delete_task(self, task: dict) -> None:
        creds = self._creds

        def _worker():
            try:
                caldav_service.delete_task(
                    **creds,
                    calendar_id=task["calendar_id"],
                    task_uid=task["uid"],
                )
            except Exception:
                pass
            GLib.idle_add(self.emit, "task-changed")

        threading.Thread(target=_worker, daemon=True).start()

    def on_edit_task(self, task: dict) -> None:
        if not self._creds:
            return
        dlg = _TaskEditDialog(
            parent=self.get_root(),
            task=task,
            calendars=self._calendars,
            mode="edit",
        )
        dlg.connect("task-saved", self._on_task_saved)
        dlg.present(self.get_root())

    def _on_new_task_clicked(self, _btn: Gtk.Button) -> None:
        if not self._creds:
            return
        # Pick default calendar (first that supports todos)
        default_cal = ""
        for g in self._groups:
            default_cal = g["calendar_id"]
            break

        dlg = _TaskEditDialog(
            parent=self.get_root(),
            task={
                "uid": "",
                "summary": "",
                "description": "",
                "due": None,
                "priority": 0,
                "calendar_id": default_cal,
                "status": "NEEDS-ACTION",
            },
            calendars=self._calendars,
            mode="create",
        )
        dlg.connect("task-saved", self._on_task_created)
        dlg.present(self.get_root())

    def _on_task_saved(self, _dlg, task: dict) -> None:
        creds = self._creds

        def _worker():
            try:
                caldav_service.update_task(
                    **creds,
                    calendar_id=task["calendar_id"],
                    task_uid=task["uid"],
                    summary=task.get("summary"),
                    description=task.get("description"),
                    due=task.get("due"),
                    priority=task.get("priority"),
                )
            except Exception:
                pass
            GLib.idle_add(self.emit, "task-changed")

        threading.Thread(target=_worker, daemon=True).start()

    def _on_task_created(self, _dlg, task: dict) -> None:
        creds = self._creds

        def _worker():
            try:
                caldav_service.create_task(
                    **creds,
                    calendar_id=task["calendar_id"],
                    summary=task.get("summary", "New Task"),
                    description=task.get("description", ""),
                    due=task.get("due"),
                    priority=task.get("priority", 0),
                )
            except Exception:
                pass
            GLib.idle_add(self.emit, "task-changed")

        threading.Thread(target=_worker, daemon=True).start()


# ── Group widget ─────────────────────────────────────────────────────────────


class _TaskGroupWidget(Gtk.Box):
    def __init__(self, group: dict, tasks_view: TasksView) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._group = group
        self._tasks_view = tasks_view
        self._collapsed = False
        self._build()

    def _build(self) -> None:
        # Group header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_start(12)
        header.set_margin_end(12)
        header.set_margin_top(8)
        header.set_margin_bottom(8)

        # Color dot using DrawingArea
        dot = Gtk.DrawingArea()
        dot.set_size_request(12, 12)
        color_hex = self._group.get("calendar_color", "#4A90D9")
        dot.set_draw_func(self._make_dot_draw(color_hex))

        name_label = Gtk.Label(label=self._group["calendar_name"])
        name_label.add_css_class("heading")
        name_label.set_halign(Gtk.Align.START)
        name_label.set_hexpand(True)

        count_label = Gtk.Label(label=str(len(self._group["tasks"])))
        count_label.add_css_class("dim-label")
        count_label.add_css_class("caption")

        self._toggle_btn = Gtk.Button.new_from_icon_name("pan-down-symbolic")
        self._toggle_btn.add_css_class("flat")
        self._toggle_btn.set_tooltip_text("Collapse")
        self._toggle_btn.connect("clicked", self._on_toggle)

        header.append(dot)
        header.append(name_label)
        header.append(count_label)
        header.append(self._toggle_btn)

        header_btn = Gtk.Button()
        header_btn.set_child(header)
        header_btn.add_css_class("flat")
        header_btn.connect("clicked", self._on_toggle)

        self.append(header_btn)

        # Task list
        self._list_box = Gtk.ListBox()
        self._list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._list_box.add_css_class("boxed-list")
        self._list_box.set_margin_start(12)
        self._list_box.set_margin_end(12)
        self._list_box.set_margin_bottom(8)

        for task in self._group["tasks"]:
            row = _TaskRow(task, self._tasks_view)
            self._list_box.append(row)

        self.append(self._list_box)
        self.append(Gtk.Separator())

    @staticmethod
    def _make_dot_draw(color_hex: str):
        def draw_func(area, cr, w, h):
            try:
                rgba = Gdk.RGBA()
                rgba.parse(color_hex)
                cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
            except Exception:
                cr.set_source_rgb(0.29, 0.56, 0.85)
            r = min(w, h) / 2
            cr.arc(w / 2, h / 2, r, 0, 2 * 3.14159)
            cr.fill()
        return draw_func

    def _on_toggle(self, _btn) -> None:
        self._collapsed = not self._collapsed
        self._list_box.set_visible(not self._collapsed)
        icon = "pan-end-symbolic" if self._collapsed else "pan-down-symbolic"
        self._toggle_btn.set_icon_name(icon)
        self._toggle_btn.set_tooltip_text(
            "Expand" if self._collapsed else "Collapse"
        )


# ── Task row ──────────────────────────────────────────────────────────────────


class _TaskRow(Adw.ActionRow):
    def __init__(self, task: dict, tasks_view: TasksView) -> None:
        super().__init__()
        self._task = task
        self._tasks_view = tasks_view
        self._build()

    def _build(self) -> None:
        task = self._task
        completed = task["status"] == "COMPLETED"

        self.set_title(task["summary"])
        if completed:
            self.add_css_class("dim-label")

        # Subtitle: due date + recurring indicator
        subtitle_parts = []
        if task.get("due"):
            try:
                due_str = task["due"]
                if "T" in due_str:
                    due_dt = datetime.fromisoformat(
                        due_str[:-1] + "+00:00" if due_str.endswith("Z") else due_str
                    )
                    subtitle_parts.append(due_dt.strftime("Due %b %d"))
                else:
                    from datetime import date
                    d = date.fromisoformat(due_str)
                    subtitle_parts.append(d.strftime("Due %b %d"))
            except Exception:
                subtitle_parts.append(f"Due {task['due']}")
        if task.get("recurring"):
            subtitle_parts.append("🔁 Recurring")
        if task.get("priority") and task["priority"] > 0:
            prio = task["priority"]
            if prio <= 3:
                subtitle_parts.append("⚡ High priority")
            elif prio <= 6:
                subtitle_parts.append("· Medium priority")
        if subtitle_parts:
            self.set_subtitle("  ·  ".join(subtitle_parts))

        # Completion checkbox (prefix)
        check = Gtk.CheckButton()
        check.set_active(completed)
        check.set_tooltip_text("Toggle completion")
        check.connect("toggled", self._on_check_toggled)
        check.set_valign(Gtk.Align.CENTER)
        self.add_prefix(check)

        # Action buttons (suffix)
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        btn_box.set_valign(Gtk.Align.CENTER)

        if not completed:
            stopwatch_btn = Gtk.Button.new_from_icon_name("media-playback-start-symbolic")
            stopwatch_btn.set_tooltip_text("Start stopwatch")
            stopwatch_btn.add_css_class("flat")
            stopwatch_btn.add_css_class("circular")
            stopwatch_btn.connect("clicked", lambda _b: self._tasks_view.on_start_timer("stopwatch", self._task))
            btn_box.append(stopwatch_btn)

            pomodoro_btn = Gtk.Button.new_from_icon_name("alarm-symbolic")
            pomodoro_btn.set_tooltip_text("Start Pomodoro")
            pomodoro_btn.add_css_class("flat")
            pomodoro_btn.add_css_class("circular")
            pomodoro_btn.connect("clicked", lambda _b: self._tasks_view.on_start_timer("pomodoro", self._task))
            btn_box.append(pomodoro_btn)

        edit_btn = Gtk.Button.new_from_icon_name("document-edit-symbolic")
        edit_btn.set_tooltip_text("Edit")
        edit_btn.add_css_class("flat")
        edit_btn.add_css_class("circular")
        edit_btn.connect("clicked", lambda _b: self._tasks_view.on_edit_task(self._task))
        btn_box.append(edit_btn)

        delete_btn = Gtk.Button.new_from_icon_name("user-trash-symbolic")
        delete_btn.set_tooltip_text("Delete")
        delete_btn.add_css_class("flat")
        delete_btn.add_css_class("circular")
        delete_btn.add_css_class("error")
        delete_btn.connect("clicked", lambda _b: self._tasks_view.on_delete_task(self._task, self))
        btn_box.append(delete_btn)

        self.add_suffix(btn_box)

    def _on_check_toggled(self, check: Gtk.CheckButton) -> None:
        # Prevent feedback loop when we programmatically toggle
        self._tasks_view.on_toggle_complete(self._task)


# ── Task edit / create dialog ─────────────────────────────────────────────────


class _TaskEditDialog(Adw.Dialog):
    __gsignals__ = {
        "task-saved": (GLib.SignalFlags.RUN_FIRST, None, (object,))
    }

    def __init__(
        self,
        parent: Gtk.Window,
        task: dict,
        calendars: list,
        mode: str,  # "edit" | "create"
    ) -> None:
        super().__init__()
        self._task = dict(task)
        self._calendars = calendars
        self._mode = mode
        self.set_title("Edit Task" if mode == "edit" else "New Task")
        self.set_content_width(420)
        self._build_ui()

    def _build_ui(self) -> None:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _b: self.close())
        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save)
        header.pack_start(cancel_btn)
        header.pack_end(save_btn)
        toolbar_view.add_top_bar(header)

        prefs_page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup()

        # Summary
        self._summary_row = Adw.EntryRow(title="Summary")
        self._summary_row.set_text(self._task.get("summary", ""))
        group.add(self._summary_row)

        # Description
        self._desc_row = Adw.EntryRow(title="Description")
        self._desc_row.set_text(self._task.get("description", "") or "")
        group.add(self._desc_row)

        # Due date
        self._due_row = Adw.EntryRow(title="Due date (YYYY-MM-DD)")
        due_val = self._task.get("due") or ""
        if due_val and "T" in due_val:
            due_val = due_val[:10]
        self._due_row.set_text(due_val)
        group.add(self._due_row)

        # Priority (Adw.SpinRow – libadwaita 1.6, available in GNOME 49)
        self._prio_row = Adw.SpinRow.new_with_range(0, 9, 1)
        self._prio_row.set_title("Priority")
        self._prio_row.set_subtitle("0 = none · 1–3 = high · 4–6 = medium · 7–9 = low")
        self._prio_row.set_value(self._task.get("priority", 0))
        group.add(self._prio_row)

        prefs_page.add(group)

        # Calendar selector (for new tasks only) – Adw.ComboRow
        if self._mode == "create" and self._calendars:
            cal_group = Adw.PreferencesGroup(title="Calendar")
            self._todo_cals = [c for c in self._calendars if c.get("supports_todos", True)]
            cal_names = [c["name"] for c in self._todo_cals]
            self._cal_row = Adw.ComboRow(title="Target calendar")
            self._cal_row.set_model(Gtk.StringList.new(cal_names))
            # Pre-select matching calendar
            active_cal = self._task.get("calendar_id", "")
            sel = 0
            for i, c in enumerate(self._todo_cals):
                if c["id"] == active_cal:
                    sel = i
                    break
            self._cal_row.set_selected(sel)
            cal_group.add(self._cal_row)
            prefs_page.add(cal_group)

        toolbar_view.set_content(prefs_page)
        self.set_child(toolbar_view)

    def _on_save(self, _btn: Gtk.Button) -> None:
        self._task["summary"] = self._summary_row.get_text().strip() or "Untitled"
        self._task["description"] = self._desc_row.get_text().strip()
        due = self._due_row.get_text().strip()
        self._task["due"] = due or None
        self._task["priority"] = int(self._prio_row.get_value())
        if self._mode == "create" and hasattr(self, "_cal_row"):
            idx = self._cal_row.get_selected()
            if 0 <= idx < len(self._todo_cals):
                self._task["calendar_id"] = self._todo_cals[idx]["id"]
        self.emit("task-saved", self._task)
        self.close()
