# SPDX-License-Identifier: GPL-3.0-or-later
"""Check runs, never used in normal use.

APP_WIDTH / APP_HEIGHT size the window, APP_ACTION calls a window method
(steps joined by "+": "select:body=moon+toggle_details"), and APP_SHOT renders the window
to a PNG, then quits (APP_SHOT_SCALE renders it at 2x or 3x, as on a denser screen).
"""
import os

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import GLib, Graphene, Gtk  # noqa: E402


def screenshot(window, path):
    """Render the window to a PNG; APP_SHOT_SCALE renders it as a denser screen would (3 for a phone)."""
    width, height = window.get_width(), window.get_height()
    scale = float(os.environ.get("APP_SHOT_SCALE", "1"))
    snapshot = Gtk.Snapshot()
    snapshot.scale(scale, scale)
    Gtk.WidgetPaintable.new(window).snapshot(snapshot, width, height)
    node = snapshot.to_node()
    if node is None:
        return
    texture = window.get_renderer().render_texture(
        node, Graphene.Rect().init(0, 0, round(width * scale), round(height * scale)))
    texture.save_to_png(path)


def prepare(window):
    if os.environ.get("APP_WIDTH"):
        window.unmaximize()
        window.set_default_size(int(os.environ["APP_WIDTH"]), int(os.environ.get("APP_HEIGHT", "760")))
    action = os.environ.get("APP_ACTION")
    shot = os.environ.get("APP_SHOT")

    def act():
        for step in filter(None, (action or "").split("+")):
            if step.startswith("select:"):
                kind, _, key = step[7:].partition("=")
                window.select((kind, int(key) if kind == "star" else key))
            elif step.startswith("find:"):
                window.open_find()
                window._find_changed(step[5:])
            elif step.startswith("look:"):
                azimuth, altitude = (float(v) for v in step[5:].split("/"))
                window.view.look(azimuth, altitude, animate=False)
            elif step.startswith("city:"):
                window.open_location()
                window._city_changed(step[5:])
            elif step.startswith("switch:"):      # click a corner switch, as a pointer would
                window.corner.controls[f"states.{int(step[7:])}"].emit("clicked")
            elif step.startswith("wheel:"):       # minutes after the day's noon
                window._time_wheels.show(float(step[6:]))
                window._time_wheels._changed()
            elif hasattr(window, step):
                getattr(window, step)()
        return False

    def capture():
        screenshot(window, shot)
        window.close()
        return False

    if action:
        GLib.timeout_add(int(os.environ.get("APP_ACT_MS", "1200")), act)
    if shot:
        GLib.timeout_add(int(os.environ.get("APP_SHOT_MS", "2600")), capture)
