"""Application entry-point."""

from __future__ import annotations

import sys
import shutil
from pathlib import Path

import gi
gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gio, Gtk, Gdk, GLib

from .windows.main_window import MainWindow


class OrbitTrackApp(Adw.Application):
    APP_ID = "io.github.jye16.OrbitTrack"

    def __init__(self) -> None:
        super().__init__(
            application_id=self.APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.connect("activate", self._on_activate)

    def _setup_icon_theme(self) -> None:
        self._install_local_desktop_assets()

        display = Gdk.Display.get_default()
        if not display:
            return

        icon_theme = Gtk.IconTheme.get_for_display(display)
        project_data_dir = Path(__file__).resolve().parent.parent / "data"
        if project_data_dir.is_dir():
            icon_theme.add_search_path(str(project_data_dir))

    def _install_local_desktop_assets(self) -> None:
        project_root = Path(__file__).resolve().parent.parent

        source_icon = project_root / "data" / f"{self.APP_ID}.svg"
        if source_icon.is_file():
            user_icon_dir = Path(GLib.get_user_data_dir()) / "icons" / "hicolor" / "scalable" / "apps"
            user_icon_dir.mkdir(parents=True, exist_ok=True)
            target_icon = user_icon_dir / f"{self.APP_ID}.svg"
            if not target_icon.exists() or source_icon.read_bytes() != target_icon.read_bytes():
                shutil.copy2(source_icon, target_icon)

        source_desktop = project_root / f"{self.APP_ID}.desktop"
        if source_desktop.is_file():
            user_app_dir = Path(GLib.get_user_data_dir()) / "applications"
            user_app_dir.mkdir(parents=True, exist_ok=True)
            target_desktop = user_app_dir / f"{self.APP_ID}.desktop"
            if not target_desktop.exists() or source_desktop.read_bytes() != target_desktop.read_bytes():
                shutil.copy2(source_desktop, target_desktop)

    def _on_activate(self, app: "OrbitTrackApp") -> None:
        self._setup_icon_theme()
        win = self.props.active_window
        if win is None:
            win = MainWindow(application=self)
        win.present()


def main() -> int:
    app = OrbitTrackApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
