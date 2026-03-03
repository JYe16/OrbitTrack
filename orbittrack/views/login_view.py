"""LoginView – CalDAV credential entry page."""

from __future__ import annotations

import gi
gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, GObject, Gtk


class LoginView(Gtk.ScrolledWindow):
    """
    Centered login form using Adw.Clamp so it looks good on any screen width.

    Signals
    -------
    login-requested(url, username, password, remember)
    """

    __gsignals__ = {
        "login-requested": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (str, str, str, bool),
        )
    }

    def __init__(self) -> None:
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.set_valign(Gtk.Align.CENTER)
        outer.set_vexpand(True)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(440)
        clamp.set_margin_top(48)
        clamp.set_margin_bottom(48)
        clamp.set_margin_start(24)
        clamp.set_margin_end(24)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.add_css_class("card")

        # ── Header ──
        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        header_box.set_margin_top(28)
        header_box.set_margin_bottom(16)
        header_box.set_margin_start(24)
        header_box.set_margin_end(24)
        header_box.set_halign(Gtk.Align.CENTER)

        icon = Gtk.Image.new_from_icon_name("alarm-symbolic")
        icon.set_pixel_size(48)
        icon.add_css_class("accent")
        header_box.append(icon)

        title = Gtk.Label(label="OrbitTrack")
        title.add_css_class("title-2")
        header_box.append(title)

        subtitle = Gtk.Label(label="Connect to your CalDAV server to start")
        subtitle.add_css_class("body")
        subtitle.add_css_class("dim-label")
        subtitle.set_wrap(True)
        subtitle.set_justify(Gtk.Justification.CENTER)
        header_box.append(subtitle)

        card.append(header_box)
        card.append(Gtk.Separator())

        # ── Form ──
        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        form.set_margin_top(20)
        form.set_margin_bottom(20)
        form.set_margin_start(24)
        form.set_margin_end(24)

        # Preferences group with entry rows
        prefs = Adw.PreferencesGroup()

        self._url_row = Adw.EntryRow(title="CalDAV URL")
        self._url_row.set_input_purpose(Gtk.InputPurpose.URL)
        self._url_row.set_text("https://")
        prefs.add(self._url_row)

        self._user_row = Adw.EntryRow(title="Username")
        self._user_row.set_input_purpose(Gtk.InputPurpose.FREE_FORM)
        prefs.add(self._user_row)

        self._pass_row = Adw.PasswordEntryRow(title="Password")
        prefs.add(self._pass_row)

        form.append(prefs)

        # Remember checkbox
        remember_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        remember_row.set_margin_start(4)
        self._remember_check = Gtk.CheckButton(label="Remember credentials")
        self._remember_check.set_active(True)
        remember_row.append(self._remember_check)
        form.append(remember_row)

        # Error label (hidden by default)
        self._error_label = Gtk.Label()
        self._error_label.add_css_class("error")
        self._error_label.set_wrap(True)
        self._error_label.set_visible(False)
        form.append(self._error_label)

        # Connect button
        self._connect_btn = Gtk.Button(label="Connect")
        self._connect_btn.add_css_class("suggested-action")
        self._connect_btn.add_css_class("pill")
        self._connect_btn.set_halign(Gtk.Align.FILL)
        self._connect_btn.connect("clicked", self._on_connect_clicked)
        form.append(self._connect_btn)

        # Spinner (hidden by default)
        self._spinner = Gtk.Spinner()
        self._spinner.set_visible(False)
        self._spinner.set_halign(Gtk.Align.CENTER)
        form.append(self._spinner)

        card.append(form)

        clamp.set_child(card)
        outer.append(clamp)
        self.set_child(outer)

        # Allow pressing Enter in any field to submit
        for row in (self._url_row, self._user_row, self._pass_row):
            row.connect("entry-activated", lambda _r: self._on_connect_clicked(None))

    # ── Public API ────────────────────────────────────────────────────────────

    def prefill(self, url: str, username: str, password: str) -> None:
        self._url_row.set_text(url)
        self._user_row.set_text(username)
        self._pass_row.set_text(password)

    def show_error(self, message: str) -> None:
        self._error_label.set_text(message)
        self._error_label.set_visible(True)

    def set_loading(self, loading: bool) -> None:
        self._connect_btn.set_visible(not loading)
        self._spinner.set_visible(loading)
        if loading:
            self._spinner.start()
            self._error_label.set_visible(False)
        else:
            self._spinner.stop()

    # ── Signals ───────────────────────────────────────────────────────────────

    def _on_connect_clicked(self, _btn) -> None:
        url = self._url_row.get_text().strip()
        username = self._user_row.get_text().strip()
        password = self._pass_row.get_text()
        remember = self._remember_check.get_active()

        if not url or not username or not password:
            self.show_error("Please fill in all fields.")
            return

        self.emit("login-requested", url, username, password, remember)
