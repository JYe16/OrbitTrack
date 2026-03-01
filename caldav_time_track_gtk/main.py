"""Application entry-point."""

from __future__ import annotations

import sys

import gi
gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gio

from .windows.main_window import MainWindow


class CalDAVTimeTrackApp(Adw.Application):
    APP_ID = "io.github.caldavtimetrack"

    def __init__(self) -> None:
        super().__init__(
            application_id=self.APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.connect("activate", self._on_activate)

    def _on_activate(self, app: "CalDAVTimeTrackApp") -> None:
        win = self.props.active_window
        if win is None:
            win = MainWindow(application=self)
        win.present()


def main() -> int:
    app = CalDAVTimeTrackApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
