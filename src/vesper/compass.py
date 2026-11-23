# SPDX-License-Identifier: GPL-3.0-or-later
"""The compass across the top of the sky: a bare, gently curled ruler.

No panel behind it. A thin line bends away at its ends as if it wrapped around
you; degrees and cardinal points ride along it and fade toward the edges. The
Moon, the bright planets and whatever you picked float above the line at their
bearing, so you can find them even when they are behind you. Colours are
LumaUI's sky card tokens, the ones Weather uses over its sky.
"""
from __future__ import annotations

import math

import cairo
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("PangoCairo", "1.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Graphene, Gtk, Pango, PangoCairo

from . import sky

try:
    from luma_appkit import type_font
except ImportError:  # pragma: no cover - outside the Luma runtime
    type_font = None

HEIGHT = 48
LINE = 18            # the line's height at its middle
CURL = 9             # how far the ends bend down
NAMES = {0: "N", 45: "NE", 90: "E", 135: "SE", 180: "S", 225: "SW", 270: "W", 315: "NW"}
MARKED = ("moon", "venus", "mars", "jupiter", "saturn", "mercury")
PLANET = {"mercury": (0.86, 0.83, 0.78), "venus": (1.0, 0.97, 0.88), "mars": (1.0, 0.62, 0.45),
          "jupiter": (1.0, 0.93, 0.80), "saturn": (0.98, 0.88, 0.66)}


def _delta(bearing: float, heading: float) -> float:
    return (bearing - heading + 180) % 360 - 180


class Compass(Gtk.Widget):
    __gtype_name__ = "VesperCompass"

    def __init__(self, sky_view, on_pick):
        super().__init__(halign=Gtk.Align.CENTER, valign=Gtk.Align.START,
                         accessible_role=Gtk.AccessibleRole.IMG)
        self.add_css_class("vesper-compass")
        self.sky_view = sky_view
        self.on_pick = on_pick
        self.side_room = 150           # kept clear on each side for the corner pill
        self._markers = []
        self._drag_heading = None
        sky_view.connect("view-changed", lambda _v: self._changed())
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", lambda _g, _x, _y: setattr(self, "_drag_heading", self.sky_view.azimuth))
        drag.connect("drag-update", self._dragged)
        drag.connect("drag-end", lambda *_a: setattr(self, "_drag_heading", None))
        self.add_controller(drag)
        click = Gtk.GestureClick()
        click.connect("released", self._clicked)
        self.add_controller(click)

    # ── size ──────────────────────────────────────────────────────────

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.VERTICAL:
            return HEIGHT, HEIGHT, -1, -1
        parent = self.get_parent()
        room = parent.get_width() if parent is not None and parent.get_width() > 0 else 700
        width = int(max(220, min(640, room - 2 * self.side_room)))
        return width, width, -1, -1

    def set_side_room(self, room: int) -> None:
        if room != self.side_room:
            self.side_room = room
            self.queue_resize()

    def _changed(self):
        heading = self.sky_view.azimuth
        self.update_property([Gtk.AccessibleProperty.LABEL],
                             [f"Compass, facing {sky.direction_name(heading)}, {heading:.0f} degrees"])
        self.queue_draw()

    @property
    def span(self) -> float:
        """Degrees across the ruler: about what the sky shows across the window."""
        view = self.sky_view
        width, height = max(1, view.get_width()), max(1, view.get_height())
        across = view.fov * width / max(width, height)
        return max(70.0, min(200.0, across * 1.15))

    # ── input ─────────────────────────────────────────────────────────

    def _dragged(self, _gesture, dx, _dy):
        if self._drag_heading is None or abs(dx) < 3:
            return
        per_degree = self.get_width() / self.span
        self.sky_view.look(self._drag_heading - dx / per_degree, self.sky_view.altitude, animate=False)

    def _clicked(self, _gesture, n_press, x, y):
        if n_press != 1:
            return
        for mx, my, selection in self._markers:
            if abs(mx - x) <= 14 and abs(my - y) <= 14:
                self.on_pick(selection)
                return

    # ── drawing ───────────────────────────────────────────────────────

    def _color(self, role, fallback="luma_sky_card_ink"):
        context = self.get_style_context()
        found, value = context.lookup_color(role)
        if not found:
            found, value = context.lookup_color(fallback)
        if not found:
            value = self.get_color()
        return (value.red, value.green, value.blue, value.alpha)

    def do_snapshot(self, snapshot):
        width, height = self.get_width(), self.get_height()
        if width <= 0 or height <= 0:
            return
        cr = snapshot.append_cairo(Graphene.Rect().init(0, 0, width, height))
        ink = self._color("luma_sky_card_ink")
        halo = self._color("lumaui_shade_night", "luma_sky_card")
        accent = self._color("luma_accent")
        heading = self.sky_view.azimuth
        span = self.span
        cx = width / 2
        half = width / 2
        per_degree = width / span

        def curve(x):
            t = (x - cx) / half
            return LINE + CURL * t * t

        def tilt(x):
            return math.atan(2 * CURL * (x - cx) / (half * half))

        def fade(x):
            return max(0.0, 1.0 - (abs(x - cx) / half) ** 3)

        # The line, fading out toward both ends.
        gradient = cairo.LinearGradient(0, 0, width, 0)
        for offset, alpha in ((0, 0), (0.18, 0.42), (0.5, 0.55), (0.82, 0.42), (1, 0)):
            gradient.add_color_stop_rgba(offset, *ink[:3], alpha)
        cr.set_source(gradient)
        cr.set_line_width(1.0)
        steps = 48
        for i in range(steps + 1):
            x = width * i / steps
            (cr.move_to if i == 0 else cr.line_to)(x, curve(x))
        cr.stroke()

        first = int(math.floor((heading - span / 2) / 5)) * 5
        for degree in range(first, int(heading + span / 2) + 6, 5):
            bearing = degree % 360
            x = cx + _delta(bearing, heading) * per_degree
            alpha = fade(x)
            if alpha <= 0.02 or x < 0 or x > width:
                continue
            y = curve(x)
            angle = tilt(x)
            if bearing in NAMES:
                major = bearing % 90 == 0
                self._tick(cr, x, y, angle, 8 if major else 6, ink, alpha * (0.95 if major else 0.75))
                self._text(cr, NAMES[bearing], x, y + 17, angle, ink, halo, alpha * (1.0 if major else 0.85),
                           role="label" if major else "caption", bold=major)
            elif bearing % 15 == 0:
                self._tick(cr, x, y, angle, 5, ink, alpha * 0.6)
                self._text(cr, str(bearing), x, y + 16, angle, ink, halo, alpha * 0.55, role="caption")
            else:
                self._tick(cr, x, y, angle, 3, ink, alpha * 0.4)

        self._markers = []
        moment = self.sky_view.moment
        if moment is not None:
            bodies = {body.key: body for body in (moment.moon, *moment.planets)}
            for key in MARKED:
                body = bodies.get(key)
                if body is None or body.altitude < 0:
                    continue
                d = _delta(body.azimuth, heading)
                if abs(d) > span / 2:
                    continue
                x = cx + d * per_degree
                y = curve(x) - 8
                alpha = fade(x)
                cr.set_source_rgba(*halo[:3], 0.55 * alpha)
                cr.arc(x, y, 5.2 if key == "moon" else 4, 0, 2 * math.pi)
                cr.fill()
                if key == "moon":
                    cr.set_source_rgba(0.97, 0.96, 0.9, alpha)
                    cr.arc(x, y, 3.8, 0, 2 * math.pi)
                else:
                    cr.set_source_rgba(*PLANET.get(key, (1, 1, 1)), alpha)
                    cr.arc(x, y, 2.5, 0, 2 * math.pi)
                cr.fill()
                self._markers.append((x, y, ("body", key)))
            self._draw_selection(cr, heading, span, per_degree, cx, width, curve, accent)

        # Where you face: a small white arrow pointing down at the line; the ruler says which way that is.
        y = curve(cx)
        cr.move_to(cx - 5.5, y - 11)
        cr.line_to(cx + 5.5, y - 11)
        cr.line_to(cx, y - 3)
        cr.close_path()
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.set_line_width(2.5)
        cr.set_source_rgba(*halo[:3], 0.6)
        cr.stroke_preserve()
        cr.set_source_rgba(*ink[:3], 1)
        cr.fill()

    def _tick(self, cr, x, y, angle, length, ink, alpha):
        cr.save()
        cr.translate(x, y)
        cr.rotate(angle)
        cr.set_source_rgba(*ink[:3], alpha)
        cr.rectangle(-0.5, 0, 1, length)
        cr.fill()
        cr.restore()

    def _draw_selection(self, cr, heading, span, per_degree, cx, width, curve, accent):
        vector = self.sky_view.vector_of(self.sky_view.selection)
        if vector is None:
            return
        azimuth, _altitude = sky.az_alt(vector)
        d = _delta(azimuth, heading)
        cr.set_source_rgba(*accent[:3], 1)
        cr.set_line_width(1.6)
        if abs(d) <= span / 2:
            x = cx + d * per_degree
            cr.arc(x, curve(x) - 8, 6.5, 0, 2 * math.pi)
            cr.stroke()
            return
        # Behind you: a chevron at the end it lies toward.
        x, sign = (width - 8, 1) if d > 0 else (8, -1)
        y = curve(x) - 8
        cr.move_to(x - 3 * sign, y - 5)
        cr.line_to(x + 2 * sign, y)
        cr.line_to(x - 3 * sign, y + 5)
        cr.stroke()

    def _text(self, cr, text, x, y, angle, ink, halo, alpha, *, role="caption", bold=False):
        """Text riding the curl, with a thin dark outline so it reads over any star."""
        layout = PangoCairo.create_layout(cr)
        font = type_font(role) if type_font else Pango.FontDescription.from_string("Sans 9")
        if bold:
            font = font.copy()
            font.set_weight(Pango.Weight.BOLD)
        layout.set_font_description(font)
        layout.set_text(text, -1)
        _ink, logical = layout.get_pixel_extents()
        cr.save()
        cr.translate(x, y)
        cr.rotate(angle)
        cr.move_to(-logical.width / 2, -logical.height / 2)
        PangoCairo.layout_path(cr, layout)
        cr.set_source_rgba(*halo[:3], 0.6 * alpha)
        cr.set_line_width(3)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.stroke()
        cr.move_to(-logical.width / 2, -logical.height / 2)
        cr.set_source_rgba(ink[0], ink[1], ink[2], ink[3] * alpha)
        PangoCairo.show_layout(cr, layout)
        cr.restore()
        cr.new_path()
