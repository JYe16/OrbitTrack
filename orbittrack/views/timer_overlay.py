"""TimerOverlay – fullscreen timer display shown on top of the main UI."""

from __future__ import annotations

import math

import gi
gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, GObject, Gtk


def _format_time(secs: int) -> str:
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class TimerOverlay(Gtk.Box):
    """
    Transparent overlay covering the full window when a timer is running.

    Signals
    -------
    timer-stopped  – emitted when the user clicks Stop
    """

    __gsignals__ = {
        "timer-stopped": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("timer-overlay")
        self._build_ui()

    def start(self, timer: dict) -> None:
        """Initialise display for a new timer."""
        self._update_display(timer)

    def tick(self, timer: dict) -> None:
        """Called every second to refresh display."""
        self._update_display(timer)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Semi-transparent backdrop
        self.add_css_class("osd")

        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        center.set_valign(Gtk.Align.CENTER)
        center.set_halign(Gtk.Align.CENTER)
        center.set_vexpand(True)
        center.set_margin_start(32)
        center.set_margin_end(32)

        # Mode label  (Stopwatch / Pomodoro – Round N / Break)
        self._mode_label = Gtk.Label()
        self._mode_label.add_css_class("title-4")
        self._mode_label.add_css_class("dim-label")
        center.append(self._mode_label)

        # Task summary
        self._task_label = Gtk.Label()
        self._task_label.add_css_class("title-1")
        self._task_label.set_wrap(True)
        self._task_label.set_justify(Gtk.Justification.CENTER)
        self._task_label.set_max_width_chars(40)
        center.append(self._task_label)

        # Analog clock (drawing area)
        self._clock = _AnalogClock()
        self._clock.set_size_request(220, 220)
        self._clock.set_halign(Gtk.Align.CENTER)
        center.append(self._clock)

        # Digital time
        self._time_label = Gtk.Label()
        self._time_label.add_css_class("display")
        center.append(self._time_label)

        # Pomodoro progress bar
        self._progress_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._progress_bar = Gtk.ProgressBar()
        self._progress_bar.set_halign(Gtk.Align.FILL)
        self._progress_bar.set_size_request(260, -1)
        self._progress_box.append(self._progress_bar)
        self._progress_box.set_visible(False)
        center.append(self._progress_box)

        # Stop button
        stop_btn = Gtk.Button(label="Stop")
        stop_btn.add_css_class("destructive-action")
        stop_btn.add_css_class("pill")
        stop_btn.set_halign(Gtk.Align.CENTER)
        stop_btn.connect("clicked", lambda _b: self.emit("timer-stopped"))
        center.append(stop_btn)

        self.append(center)

    def _update_display(self, timer: dict) -> None:
        mode = timer.get("mode", "stopwatch")
        phase = timer.get("phase", "work")
        elapsed = timer.get("elapsed_secs", 0)
        pom_secs = timer.get("pomodoro_secs", 25 * 60)
        rnd = timer.get("round", 1)

        # Mode label
        if mode == "stopwatch":
            self._mode_label.set_text("Stopwatch")
        elif mode == "pomodoro":
            if phase == "break":
                self._mode_label.set_text("Break ☕")
            else:
                self._mode_label.set_text(f"Pomodoro · Round {rnd}")

        self._task_label.set_text(timer.get("summary", ""))

        # Pomodoro: count down; stopwatch: count up
        if mode == "pomodoro" and phase == "work":
            remaining = max(0, pom_secs - elapsed)
            self._time_label.set_text(_format_time(remaining))
            frac = elapsed / pom_secs if pom_secs else 0
            self._progress_bar.set_fraction(min(1.0, frac))
            self._progress_box.set_visible(True)
            self._clock.set_angle_fraction(frac, elapsed)
        elif mode == "pomodoro" and phase == "break":
            break_secs = 5 * 60
            remaining = max(0, break_secs - elapsed)
            self._time_label.set_text(_format_time(remaining))
            frac = elapsed / break_secs if break_secs else 0
            self._progress_bar.set_fraction(min(1.0, frac))
            self._progress_box.set_visible(True)
            self._clock.set_angle_fraction(frac, elapsed)
        else:
            self._time_label.set_text(_format_time(elapsed))
            self._progress_box.set_visible(False)
            # Stopwatch: rotate continuously (one full rotation = 60 s)
            self._clock.set_elapsed(elapsed)


# ── Analog clock drawing area ─────────────────────────────────────────────────


class _AnalogClock(Gtk.DrawingArea):
    def __init__(self) -> None:
        super().__init__()
        self._elapsed = 0
        self._frac: float | None = None
        self.set_draw_func(self._draw)

    def set_elapsed(self, elapsed: int) -> None:
        self._elapsed = elapsed
        self._frac = None
        self.queue_draw()

    def set_angle_fraction(self, frac: float, elapsed: int = 0) -> None:
        self._frac = frac
        self._elapsed = elapsed
        self.queue_draw()

    def _draw(self, area, cr, w, h) -> None:
        cx, cy = w / 2, h / 2
        r = min(w, h) / 2 - 4

        # Background circle
        cr.set_source_rgba(0.15, 0.15, 0.18, 0.85)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.fill()

        # Tick marks
        cr.set_source_rgba(0.55, 0.55, 0.60, 0.7)
        cr.set_line_width(1.5)
        for i in range(12):
            angle = math.pi * 2 * i / 12 - math.pi / 2
            x1 = cx + (r - 6) * math.cos(angle)
            y1 = cy + (r - 6) * math.sin(angle)
            x2 = cx + r * math.cos(angle)
            y2 = cy + r * math.sin(angle)
            cr.move_to(x1, y1)
            cr.line_to(x2, y2)
            cr.stroke()

        elapsed = self._elapsed
        frac = self._frac

        # Second hand (red)
        sec_angle = elapsed % 60 / 60 * 2 * math.pi - math.pi / 2
        cr.set_source_rgb(0.96, 0.26, 0.21)
        cr.set_line_width(2.0)
        cr.move_to(cx, cy)
        cr.line_to(cx + (r * 0.85) * math.cos(sec_angle), cy + (r * 0.85) * math.sin(sec_angle))
        cr.stroke()

        # Minute hand
        minute_angle = (elapsed % 3600) / 3600 * 2 * math.pi - math.pi / 2
        cr.set_source_rgba(0.9, 0.9, 0.9, 0.9)
        cr.set_line_width(3.0)
        cr.move_to(cx, cy)
        cr.line_to(cx + (r * 0.65) * math.cos(minute_angle), cy + (r * 0.65) * math.sin(minute_angle))
        cr.stroke()

        # Hour hand
        hour_angle = (elapsed % 43200) / 43200 * 2 * math.pi - math.pi / 2
        cr.set_source_rgba(0.9, 0.9, 0.9, 0.9)
        cr.set_line_width(4.5)
        cr.move_to(cx, cy)
        cr.line_to(cx + (r * 0.45) * math.cos(hour_angle), cy + (r * 0.45) * math.sin(hour_angle))
        cr.stroke()

        # Progress arc for pomodoro
        if frac is not None and frac > 0:
            start_angle = -math.pi / 2
            end_angle = start_angle + frac * 2 * math.pi
            cr.set_source_rgba(0.38, 0.68, 0.91, 0.4)
            cr.set_line_width(5)
            cr.arc(cx, cy, r - 3, start_angle, end_angle)
            cr.stroke()

        # Center dot
        cr.set_source_rgba(0.9, 0.9, 0.9, 1)
        cr.arc(cx, cy, 4, 0, 2 * math.pi)
        cr.fill()
