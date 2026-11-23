# SPDX-License-Identifier: GPL-3.0-or-later
"""The time wheels in the Time panel, the way Luma's Clock sets an alarm.

Two wheels over an inset band: the hour and the minute. The chosen value sits
in the band with two neighbours either side fading out. Scroll, drag (a step
per 40 px, and a flick keeps it turning), tap a neighbour, or use the arrow
keys. The hours run
noon to noon, so turning past 23 carries on into the small hours of the same
night instead of jumping back to the afternoon.
"""
from __future__ import annotations

from typing import Callable, Sequence

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk

try:
    from luma_appkit import apply_type, motion_duration
except ImportError:  # pragma: no cover - outside the Luma runtime
    apply_type = lambda _widget, _role: None
    motion_duration = lambda ms: ms

ROWS = 5
STEP = 40

class Wheel(Gtk.Box):
    """One wheel. `wraps` lets it turn round (minutes); otherwise it stops at its ends."""

    __gtype_name__ = "VesperWheel"

    def __init__(self, name: str, values: Sequence[str], on_change: Callable[[int], None], *,
                 wraps: bool = False) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, focusable=True,
                         accessible_role=Gtk.AccessibleRole.SPIN_BUTTON)
        self.add_css_class("vesper-wheel")
        self.values = list(values)
        self.wraps = wraps
        self.index = 0
        self.on_change = on_change
        self._drag_rows = 0
        self._coast = 0              # rows still to turn after a flick
        self._coast_source = 0
        self.rows = []
        for _ in range(ROWS):
            row = Gtk.Label(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
            row.set_size_request(-1, STEP)
            apply_type(row, "title-1")
            row.add_css_class("vesper-wheel-item")
            self.rows.append(row)
            self.append(row)
        self.update_property([Gtk.AccessibleProperty.LABEL], [name])
        scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL
                                           | Gtk.EventControllerScrollFlags.DISCRETE)
        scroll.connect("scroll", lambda _c, _dx, dy: self._turn(1 if dy > 0 else -1) or True)
        self.add_controller(scroll)
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._drag_begin)
        drag.connect("drag-update", self._dragged)
        drag.connect("drag-end", self._drag_end)
        self.add_controller(drag)
        swipe = Gtk.GestureSwipe()
        swipe.connect("swipe", self._flicked)
        self.add_controller(swipe)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._key)
        self.add_controller(keys)
        self._show()

    @property
    def value(self) -> str:
        return self.values[self.index]

    def set_index(self, index: int) -> None:
        """Show `index` without telling anyone (the panel is catching up with the time)."""
        index = index % len(self.values) if self.wraps else max(0, min(len(self.values) - 1, index))
        if index != self.index:
            self.index = index
            self._show()

    def _drag_begin(self, _gesture, _x, _y):
        self._drag_rows = 0
        self._stop_coasting()
        self.grab_focus()

    def _dragged(self, _gesture, _dx: float, dy: float) -> None:
        rows = int(-dy / STEP)
        if rows != self._drag_rows:
            self._turn(rows - self._drag_rows)
            self._drag_rows = rows

    def _drag_end(self, gesture, dx: float, dy: float) -> None:
        # Barely moved: a tap, which picks the row under the finger.
        if self._drag_rows == 0 and abs(dx) < 6 and abs(dy) < 6:
            _ok, _x, y = gesture.get_start_point()
            offset = int(y // STEP) - ROWS // 2
            if offset:
                self._turn(offset)

    def _flicked(self, _gesture, _vx: float, vy: float) -> None:
        """A flick turns on by its speed, slowing to a stop, as a phone's wheel does."""
        rows = int(-vy / 260)
        if abs(rows) < 2:
            return
        if motion_duration(300) == 0:       # Reduced Motion: land at once, no coasting
            self._turn(max(-30, min(30, rows)))
            return
        self._coast = max(-30, min(30, rows))
        self._stop_source()
        self._coast_source = GLib.timeout_add(30, self._coast_step)

    def _coast_step(self):
        if self._coast == 0:
            self._coast_source = 0
            return GLib.SOURCE_REMOVE
        step = 1 if self._coast > 0 else -1
        before = self.index
        self._turn(step)
        self._coast -= step
        if self.index == before:            # an end stops it
            self._coast = 0
        # Slower as it runs out: each step waits a little longer.
        if self._coast:
            self._coast_source = GLib.timeout_add(int(30 + 260 / (abs(self._coast) + 2)), self._coast_step)
            return GLib.SOURCE_REMOVE
        self._coast_source = 0
        return GLib.SOURCE_REMOVE

    def _stop_source(self):
        if self._coast_source:
            GLib.source_remove(self._coast_source)
            self._coast_source = 0

    def _stop_coasting(self):
        self._coast = 0
        self._stop_source()

    def _key(self, _controller, keyval: int, _code: int, _state) -> bool:
        steps = {Gdk.KEY_Up: -1, Gdk.KEY_KP_Up: -1, Gdk.KEY_Down: 1, Gdk.KEY_KP_Down: 1,
                 Gdk.KEY_Page_Up: -3, Gdk.KEY_Page_Down: 3}
        if keyval in steps:
            self._turn(steps[keyval])
            return True
        return False

    def _turn(self, steps: int) -> None:
        before = self.index
        self.set_index(self.index + steps)
        if self.index != before:
            self.on_change(self.index)

    def _show(self) -> None:
        middle = ROWS // 2
        count = len(self.values)
        for offset, row in enumerate(self.rows):
            at = self.index + offset - middle
            if self.wraps:
                at %= count
            row.set_text(self.values[at] if 0 <= at < count else "")
            for css, on in (("on", offset == middle), ("near", abs(offset - middle) == 1),
                            ("far", abs(offset - middle) == 2)):
                (row.add_css_class if on else row.remove_css_class)(css)
        self.update_property([Gtk.AccessibleProperty.VALUE_TEXT], [self.value])


class TimeWheels(Gtk.Overlay):
    """Hour : minutes over the band. `on_change(minutes)` gets minutes after the day's noon."""

    __gtype_name__ = "VesperTimeWheels"

    def __init__(self, hour_names: Sequence[str], on_change: Callable[[int], None]) -> None:
        band_holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        band_holder.set_size_request(-1, ROWS * STEP)
        band = Gtk.Box(valign=Gtk.Align.CENTER, vexpand=True, can_target=False)
        band.add_css_class("vesper-wheel-band")
        band.set_size_request(-1, STEP)
        band_holder.append(band)
        super().__init__(child=band_holder)
        self.on_change = on_change
        self.hours = Wheel("Hour", hour_names, lambda _i: self._changed())
        self.minutes = Wheel("Minutes", [f"{m:02d}" for m in range(60)], lambda _i: self._changed(),
                             wraps=True)
        colon = Gtk.Label(label=":", can_target=False)
        apply_type(colon, "title-1")
        colon.add_css_class("vesper-wheel-colon")
        wheels = Gtk.Box(halign=Gtk.Align.CENTER, spacing=4)
        wheels.add_css_class("vesper-wheels")
        wheels.append(self.hours)
        wheels.append(colon)
        wheels.append(self.minutes)
        self.add_overlay(wheels)
        self.set_measure_overlay(wheels, True)

    def set_hour_names(self, names: Sequence[str]) -> None:
        self.hours.values = list(names)
        self.hours._show()

    def show(self, minutes: float) -> None:
        """Turn the wheels to `minutes` after noon."""
        whole = max(0, min(24 * 60 - 1, int(minutes)))
        self.hours.set_index(whole // 60)
        self.minutes.set_index(whole % 60)

    def _changed(self) -> None:
        self.on_change(self.hours.index * 60 + self.minutes.index)
