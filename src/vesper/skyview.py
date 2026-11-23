# SPDX-License-Identifier: GPL-3.0-or-later
"""The sky itself: Vesper's one piece of drawn content.

A stereographic view of the horizontal sky. Colours come from LumaUI's sky
tokens (the same ones Weather paints with); stars take their own colour from
their temperature, the way a photo takes the colour of what it shows.
"""
from __future__ import annotations

import math
import random
import time

import cairo
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("PangoCairo", "1.0")
gi.require_version("Graphene", "1.0")
from gi.repository import GLib, GObject, Graphene, Gtk, Pango, PangoCairo

try:
    gi.require_version("Adw", "1")
    from gi.repository import Adw
except (ValueError, ImportError):  # pragma: no cover - outside a libadwaita session
    Adw = None

from . import sky

try:
    from luma_appkit import type_font
except ImportError:  # pragma: no cover - outside the Luma runtime
    type_font = None
try:
    from luma_appkit.lumaui import motion_duration
except ImportError:  # pragma: no cover
    def motion_duration(ms):
        return ms

MIN_FOV, MAX_FOV, DEFAULT_FOV = 30.0, 130.0, 120.0
PLANET_TINTS = {
    "mercury": (0.86, 0.83, 0.78), "venus": (1.0, 0.97, 0.88), "mars": (1.0, 0.62, 0.45),
    "jupiter": (1.0, 0.93, 0.80), "saturn": (0.98, 0.88, 0.66), "uranus": (0.72, 0.92, 0.95),
    "neptune": (0.62, 0.74, 1.0),
}
# Black-body tints by B-V colour index (Mitchell Charity's table, desaturated toward white).
_BV = ((-0.4, (0.64, 0.73, 1.0)), (0.0, (0.80, 0.86, 1.0)), (0.4, (0.95, 0.95, 1.0)),
       (0.6, (1.0, 0.96, 0.90)), (1.0, (1.0, 0.86, 0.70)), (1.5, (1.0, 0.76, 0.52)), (2.0, (1.0, 0.66, 0.40)))


def star_tint(bv: float) -> tuple[float, float, float]:
    if bv <= _BV[0][0]:
        return _BV[0][1]
    for (b0, c0), (b1, c1) in zip(_BV, _BV[1:]):
        if bv <= b1:
            t = (bv - b0) / (b1 - b0)
            return tuple(a + (b - a) * t for a, b in zip(c0, c1))
    return _BV[-1][1]


def limiting_magnitude(sun_altitude: float) -> float:
    """How faint a star you can see, from full day to a dark sky."""
    points = ((-18, 6.2), (-12, 5.2), (-6, 3.0), (-2, 1.0), (0, -1.0), (8, -2.5))
    if sun_altitude <= points[0][0]:
        return points[0][1]
    for (a0, m0), (a1, m1) in zip(points, points[1:]):
        if sun_altitude <= a1:
            return m0 + (m1 - m0) * (sun_altitude - a0) / (a1 - a0)
    return points[-1][1]


class SkyView(Gtk.Widget):
    """Drag to look around, pinch or scroll to zoom, tap to pick."""

    __gtype_name__ = "VesperSkyView"
    __gsignals__ = {
        "picked": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "view-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, catalog: sky.Catalog):
        super().__init__(hexpand=True, vexpand=True, focusable=True, can_focus=True,
                         accessible_role=Gtk.AccessibleRole.IMG)
        self.add_css_class("vesper-sky")
        self.catalog = catalog
        self.moment: sky.Moment | None = None
        self.azimuth = 180.0
        self.altitude = 32.0
        self.fov = DEFAULT_FOV
        self.show_figures = True
        self.show_labels = True
        self.show_milky_way = True
        self.selection: tuple | None = None     # ("star", index) | ("body", key)
        self.bottom_inset = 0                   # room the action bar takes over the sky
        self.top_inset = 0
        self._stars_h = []
        self._milky_h = []
        self._faint_h = []
        self._figures_h = {}
        self._dust, self._dust_strength, self._glow_strength = _milky_dust(catalog)
        self._dust_h = []
        self._targets = []
        self._drag_start = None
        self._zoom_start = None
        self._moved = False
        self._animation = 0
        self.frame_horizon = False              # place the horizon low on the first draw
        self.reserved = lambda: []              # boxes over the sky (compass, corner) that names avoid

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._drag_begin)
        drag.connect("drag-update", self._drag_update)
        drag.connect("drag-end", self._drag_end)
        self.add_controller(drag)
        click = Gtk.GestureClick()
        click.connect("released", self._released)
        self.add_controller(click)
        zoom = Gtk.GestureZoom()
        zoom.connect("begin", lambda g, s: setattr(self, "_zoom_start", self.fov))
        zoom.connect("scale-changed", self._zoomed)
        self.add_controller(zoom)
        scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect("scroll", self._scrolled)
        self.add_controller(scroll)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._key)
        self._high_contrast = _read_high_contrast()
        if Adw is not None:     # high contrast changes how the sky is painted, live
            try:
                Adw.StyleManager.get_default().connect("notify::high-contrast", self._contrast_changed)
            except Exception:  # noqa: BLE001 - no display, as in previews
                pass
        self.add_controller(keys)

    # ── state ─────────────────────────────────────────────────────────

    def set_moment(self, moment: sky.Moment) -> None:
        self.moment = moment
        to_h = moment.to_horizontal
        self._stars_h = [to_h(v) for v in self.catalog.vectors]
        self._milky_h = [to_h(v) for v in self.catalog.milky_vectors]
        self._faint_h = [to_h(v) for v in self.catalog.faint_vectors]
        self._dust_h = [to_h(v) for v in self._dust]
        self._figures_h = {key: [[to_h(v) for v in line] for line in figure]
                           for key, figure in self.catalog.line_vectors.items()}
        self._describe()
        self.queue_draw()

    def set_options(self, *, figures: bool | None = None, labels: bool | None = None,
                    milky_way: bool | None = None) -> None:
        if milky_way is not None:
            self.show_milky_way = milky_way
        if figures is not None:
            self.show_figures = figures
        if labels is not None:
            self.show_labels = labels
        self.queue_draw()

    def select(self, selection: tuple | None) -> None:
        self.selection = selection
        self.queue_draw()

    def look(self, azimuth: float, altitude: float, fov: float | None = None, animate: bool = True) -> None:
        """Turn to a direction, gliding there unless motion is reduced."""
        fov = self._clamp_fov(fov or self.fov)
        previous, self.fov = self.fov, fov          # the lowest altitude depends on the zoom
        low = self.lowest_altitude()
        self.fov = previous
        target = (azimuth % 360, max(low, min(90.0, altitude)), fov)
        duration = motion_duration(420) if animate else 0
        if self._animation:
            self.remove_tick_callback(self._animation)
            self._animation = 0
        if duration <= 0:
            self.azimuth, self.altitude, self.fov = target
            self._changed()
            return
        start = (self.azimuth, self.altitude, self.fov)
        turn = (target[0] - start[0] + 180) % 360 - 180
        began = time.monotonic()

        def tick(_widget, _clock):
            t = min(1.0, (time.monotonic() - began) * 1000 / duration)
            ease = 1 - (1 - t) ** 3
            self.azimuth = (start[0] + turn * ease) % 360
            self.altitude = start[1] + (target[1] - start[1]) * ease
            self.fov = start[2] + (target[2] - start[2]) * ease
            self._changed()
            if t >= 1.0:
                self._animation = 0
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE
        self._animation = self.add_tick_callback(tick)

    def look_at(self, selection: tuple) -> None:
        vector = self.vector_of(selection)
        if vector is None:
            return
        azimuth, altitude = sky.az_alt(vector)
        # Keep the horizon in sight for things that are low.
        self.look(azimuth, max(altitude, min(25.0, self.fov / 4)), min(self.fov, 90.0))

    def vector_of(self, selection: tuple | None):
        if selection is None or self.moment is None:
            return None
        kind, key = selection
        if kind == "star":
            return self._stars_h[key]
        if kind == "constellation":
            entry = self.catalog.constellations.get(key)
            return self.moment.to_horizontal(sky.unit(entry["ra"], entry["dec"])) if entry else None
        for body in (self.moment.sun, self.moment.moon, *self.moment.planets):
            if body.key == key:
                return body.vector
        return None

    def resting_altitude(self, width: float, height: float, share: float = 0.95) -> float:
        """How high to look so the horizon sits at `share` of the height: a strip of land under the sky."""
        scale = (max(width, height) / 2) / math.tan(math.radians(self.fov) / 4)
        cy = self.top_inset + (height - self.top_inset - self.bottom_inset) / 2
        below = max(1.0, height * share - cy)
        return max(1.0, min(70.0, math.degrees(2 * math.atan(below / scale))))

    def lowest_altitude(self) -> float:
        """The lowest you can look: the horizon never climbs above the last tenth or so of the view.

        There is nothing to see in the ground, so it never takes more than a thin strip.
        """
        width, height = self.get_width(), self.get_height()
        if width <= 0 or height <= 0:
            return 1.0
        return self.resting_altitude(width, height, share=0.92)

    def _clamp_altitude(self, altitude: float) -> float:
        return max(self.lowest_altitude(), min(90.0, altitude))

    def zoom_by(self, factor: float) -> None:
        self.fov = self._clamp_fov(self.fov * factor)
        self.altitude = self._clamp_altitude(self.altitude)
        self._changed()

    @staticmethod
    def _clamp_fov(fov: float) -> float:
        return max(MIN_FOV, min(MAX_FOV, fov))

    def _changed(self) -> None:
        self._describe()
        self.queue_draw()
        self.emit("view-changed")

    def _describe(self) -> None:
        direction = sky.direction_name(self.azimuth)
        where = "straight up" if self.altitude > 75 else f"to the {direction}"
        self.update_property([Gtk.AccessibleProperty.LABEL], [f"The sky, looking {where}"])

    # ── projection ────────────────────────────────────────────────────

    def _frame(self, width: float, height: float):
        az, alt = math.radians(self.azimuth), math.radians(self.altitude)
        forward = (math.cos(alt) * math.cos(az), -math.cos(alt) * math.sin(az), math.sin(alt))
        right = (-math.sin(az), -math.cos(az), 0.0)
        up = (-math.sin(alt) * math.cos(az), math.sin(alt) * math.sin(az), math.cos(alt))
        scale = (max(width, height) / 2) / math.tan(math.radians(self.fov) / 4)
        cx = width / 2
        cy = self.top_inset + (height - self.top_inset - self.bottom_inset) / 2
        return forward, right, up, scale, cx, cy

    @staticmethod
    def _project(v, frame):
        forward, right, up, scale, cx, cy = frame
        f = v[0] * forward[0] + v[1] * forward[1] + v[2] * forward[2]
        if f < -0.85:
            return None
        k = scale / (1 + f)
        return (cx + (v[0] * right[0] + v[1] * right[1] + v[2] * right[2]) * k,
                cy - (v[0] * up[0] + v[1] * up[1] + v[2] * up[2]) * k, k)

    # ── drawing ───────────────────────────────────────────────────────

    def _color(self, role: str, fallback: str = "luma_sky_card_ink"):
        context = self.get_style_context()
        found, value = context.lookup_color(role)
        if not found:
            found, value = context.lookup_color(fallback)
        if not found:
            value = self.get_color()
        return (value.red, value.green, value.blue, value.alpha)

    @property
    def high_contrast(self) -> bool:
        """In high contrast the sky is plain black under white stars and lines: no glow, no gradient.

        (Luma's high-contrast tokens turn every sky colour into the ink, which would paint the sky white.)
        """
        return self._high_contrast

    def _contrast_changed(self, *_args) -> None:
        self._high_contrast = _read_high_contrast()
        self.queue_draw()

    def _sky_stops(self, sun_altitude: float):
        if self.high_contrast:
            return [(0.0, 0.0, 0.0, 1.0)] * 3
        def triple(name):
            return [self._color(f"luma_weather_sky_{name}_{i}", "lumaui_shade_night") for i in (1, 2, 3)]
        night, dusk, day = triple("night"), triple("dusk"), triple("day")
        # A dark night is deepest overhead: Weather's night, taken down toward its own shade.
        deep = self._color("lumaui_shade_night", "luma_weather_sky_night_1")
        night = [_mix(night[0], deep, 0.5), night[0], _mix(night[0], night[1], 0.55)]
        if sun_altitude <= -14:
            return night
        if sun_altitude <= -4:
            t = (sun_altitude + 14) / 10
            return [_mix(a, b, t) for a, b in zip(night, dusk)]
        if sun_altitude <= 4:
            t = (sun_altitude + 4) / 8
            return [_mix(a, b, t) for a, b in zip(dusk, day)]
        return day

    def do_snapshot(self, snapshot):
        width, height = self.get_width(), self.get_height()
        if width <= 0 or height <= 0:
            return
        rect = Graphene.Rect().init(0, 0, width, height)
        if self.frame_horizon:
            self.frame_horizon = False
            self.altitude = self.resting_altitude(width, height)
        elif self.altitude < self.lowest_altitude() - 0.01 and not self._animation:
            self.altitude = self.lowest_altitude()      # the window grew: keep the ground a strip
        frame = self._frame(width, height)
        self._draw_background(snapshot.append_cairo(rect), width, height)
        if self.moment is None:
            return
        self._draw_sky(snapshot.append_cairo(rect), frame, width, height)

    def _draw(self, cr, width, height):
        """Everything in one cairo pass (previews and tests)."""
        frame = self._frame(width, height)
        self._draw_background(cr, width, height)
        if self.moment is not None:
            self._draw_sky(cr, frame, width, height)

    def _draw_sky(self, cr, frame, width, height):
        limit, visibility = self._seeing()
        if visibility > 0.05 and self.show_milky_way and not self.high_contrast:
            self._draw_milky_way(cr, frame, width, height, self._color("luma_sky_card_ink"), visibility)
        self._draw_main(cr, frame, width, height, limit, visibility)

    def _seeing(self):
        sun_altitude = self.moment.sun.altitude
        limit = limiting_magnitude(sun_altitude)
        # Seen through a narrow field, fainter stars come out.
        limit += max(0.0, (90 - self.fov) / 60)
        return limit, max(0.0, min(1.0, (limit - 1.0) / 4.0))

    def _draw_background(self, cr, width, height):
        # The sky's colour follows altitude: deepest at the zenith, lightest at the horizon.
        sun_altitude = self.moment.sun.altitude if self.moment else -30
        frame = self._frame(width, height)
        zenith = self._project((0.0, 0.0, 1.0), frame)
        horizon = self._project(sky.horizontal(self.azimuth, 0), frame)
        top = zenith[1] if zenith else -height
        bottom = horizon[1] if horizon else height
        if bottom - top < 40:
            top, bottom = 0, height
        gradient = cairo.LinearGradient(0, top, 0, bottom)
        for offset, color in zip((0.0, 0.55, 1.0), self._sky_stops(sun_altitude)):
            gradient.add_color_stop_rgba(offset, *color)
        cr.set_source(gradient)
        cr.paint()

    def _draw_main(self, cr, frame, width, height, limit, visibility):
        targets = []
        ink = self._color("luma_sky_card_ink")
        if self.show_figures and visibility > 0.1:
            self._draw_figures(cr, frame, ink, visibility)
        self._draw_stars(cr, frame, limit, targets)
        self._draw_bodies(cr, frame, ink, targets)
        self._draw_ground(cr, frame, width, height)
        if self.show_labels:
            self._draw_labels(cr, frame, ink, limit, width, height)
        self._draw_selection(cr, frame)
        self._targets = targets

    def _draw_milky_way(self, cr, frame, width, height, ink, visibility):
        """Starlight, not fog: a faint, patchy glow with a dust of unresolved stars over it.

        The glow is painted at a fraction of the size, softened, then enlarged; the
        dust is single pixels. Cheap on purpose: Luma also runs where there is no
        GPU, and a blur over the whole window on every frame costs whole cores there.
        """
        # It only shows once the sky is properly dark: from the Sun 12° down, fully by 18°.
        visibility *= max(0.0, min(1.0, (-self.moment.sun.altitude - 12) / 6))
        if visibility <= 0.02:
            return
        # A cool white, bluer than the ink: the Milky Way is the light of hot young stars.
        r, g, b = _mix(ink[:3], (0.74, 0.81, 1.0), 0.6)
        self._draw_glow(cr, frame, width, height, (r, g, b), visibility)
        self._draw_dust(cr, frame, width, height, (r, g, b), visibility)

    def _draw_glow(self, cr, frame, width, height, color, visibility):
        spacing = math.radians(1.5)
        # Zoomed in, the glow resolves into stars: it fades out below a 70° field.
        visibility *= max(0.0, min(1.0, (self.fov - 30) / 40))
        if visibility <= 0.02:
            return
        # Each glow point covers about three pixels of the small surface, whatever the zoom,
        # so the softening below always spans the same share of a point.
        point = spacing * frame[3] / 2 * 0.8
        step = max(4, int(point / 1.7))
        w, h = int(width / step) + 3, int(height / step) + 3
        small = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        pen = cairo.Context(small)
        pen.scale(1 / step, 1 / step)
        base = 0.021 * visibility
        for v, point, patch in zip(self._milky_h, self.catalog.milky_way, self._glow_strength):
            if v[2] < -0.03:
                continue
            p = self._project(v, frame)
            if p is None:
                continue
            x, y, k = p
            radius = spacing * k * 1.15         # overlapping, so the grid never shows
            if x < -radius or y < -radius or x > width + radius or y > height + radius:
                continue
            # The bright core carries it, the faint outskirts barely show; a little patchy, as star
            # clouds are; dimmer low down, where its light crosses the most air.
            low = (0.12 + 0.88 * min(1.0, v[2] / 0.32) ** 1.4) if v[2] >= 0 else 0.12 * sinking(v[2])
            pen.set_source_rgba(*color, base * BRIGHTNESS[point[2]] * patch * low)
            pen.arc(x, y, radius, 0, 2 * math.pi)
            pen.fill()
        soft = _box_blur(_box_blur(_box_blur(small)))
        cr.save()
        cr.scale(step, step)
        pattern = cairo.SurfacePattern(soft)
        pattern.set_filter(cairo.FILTER_BILINEAR)
        cr.set_source(pattern)
        cr.paint()
        cr.restore()

    def _draw_dust(self, cr, frame, width, height, color, visibility):
        """Single-pixel grains where the Milky Way is brightest: the stars too faint to tell apart."""
        visibility *= max(0.0, min(1.0, (self.fov - 18) / 30))
        if visibility <= 0.02:
            return
        forward, _right, _up, scale, _cx, _cy = frame
        reach = math.cos(min(math.pi * 0.95, 2 * math.atan(math.hypot(width / 2, height / 2) / scale)))
        fx, fy, fz = forward
        levels = ([], [], [], [])
        for v, strength in zip(self._dust_h, self._dust_strength):
            if v[2] < 0.02 or v[0] * fx + v[1] * fy + v[2] * fz < reach:
                continue
            p = self._project(v, frame)
            if p is None:
                continue
            x, y, _k = p
            if 0 <= x < width and 0 <= y < height:
                # Low down the air dims them like everything else.
                levels[min(3, int(strength * (0.3 + 0.7 * min(1.0, v[2] / 0.32)) * 4))].append((x, y))
        for level, points in enumerate(levels):
            if not points:
                continue
            for x, y in points:
                cr.rectangle(int(x), int(y), 1, 1)
            cr.set_source_rgba(*color, (0.09 + 0.08 * level) * visibility)
            cr.fill()

    def _draw_figures(self, cr, frame, ink, visibility):
        r, g, b, _a = ink
        cr.set_line_width(0.9)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        low = []            # segments near the horizon, drawn fainter
        for figure in self._figures_h.values():
            for line in figure:
                for u, w in zip(line, line[1:]):
                    if u[2] <= 0 and w[2] <= 0:
                        continue                    # wholly below the horizon
                    if u[2] < 0 or w[2] < 0:
                        # Crossing it: end the segment where it meets the horizon.
                        above, below = (u, w) if u[2] > 0 else (w, u)
                        t = above[2] / (above[2] - below[2])
                        u, w = above, tuple(above[i] + (below[i] - above[i]) * t for i in range(3))
                    pu, pw = self._project(u, frame), self._project(w, frame)
                    if pu is None or pw is None:
                        continue
                    if min(u[2], w[2]) > 0.07:
                        cr.move_to(pu[0], pu[1])
                        cr.line_to(pw[0], pw[1])
                    else:
                        low.append((pu[0], pu[1], pw[0], pw[1]))
        strong = self.high_contrast
        cr.set_source_rgba(r, g, b, (0.5 if strong else 0.12) * visibility)
        cr.stroke()
        for x1, y1, x2, y2 in low:
            cr.move_to(x1, y1)
            cr.line_to(x2, y2)
        cr.set_source_rgba(r, g, b, (0.25 if strong else 0.05) * visibility)
        cr.stroke()

    def _draw_stars(self, cr, frame, limit, targets):
        width = frame[4] * 2
        height = frame[5] * 2 + 400
        zoom = max(1.0, (DEFAULT_FOV / self.fov) ** 0.35)
        if limit > 6.0:
            self._draw_faint(cr, frame, limit, width, height)
        for index, (v, star) in enumerate(zip(self._stars_h, self.catalog.stars)):
            magnitude = star[2] + extinction(v[2])
            if magnitude > limit:
                continue
            p = self._project(v, frame)
            if p is None:
                continue
            x, y, _k = p
            if x < -8 or y < -8 or x > width + 8 or y > height:
                continue
            brightness = limit - magnitude
            radius = min(4.8, 0.6 + brightness * 0.45) * zoom
            alpha = max(0.38, min(1.0, 0.36 + brightness / 3.0))
            tint = star_tint(star[3])
            if magnitude < 2.6:
                # Bright stars bloom softly, the way they do to the eye.
                reach = radius * (5.5 if magnitude < 1 else 4)
                glow = cairo.RadialGradient(x, y, radius * 0.5, x, y, reach)
                glow.add_color_stop_rgba(0, *tint, 0.42 * alpha)
                glow.add_color_stop_rgba(0.35, *tint, 0.12 * alpha)
                glow.add_color_stop_rgba(1, *tint, 0.0)
                cr.set_source(glow)
                cr.arc(x, y, reach, 0, 2 * math.pi)
                cr.fill()
            cr.set_source_rgba(*tint, alpha)
            cr.arc(x, y, radius, 0, 2 * math.pi)
            cr.fill()
            if magnitude < 4.5 and v[2] > 0:
                targets.append((x, y, ("star", index), magnitude))

    def _draw_faint(self, cr, frame, limit, width, height):
        """The stars beyond the naked eye's usual reach, for a sky that fills in as you zoom."""
        forward, _right, _up, scale, _cx, _cy = frame
        # Only what lies within the view's corners is worth projecting.
        reach = math.cos(min(math.pi * 0.95, 2 * math.atan(math.hypot(width / 2, height / 2) / scale)))
        fx, fy, fz = forward
        for v, star in zip(self._faint_h, self.catalog.faint):
            if v[0] * fx + v[1] * fy + v[2] * fz < reach:
                continue
            magnitude = star[2] + extinction(v[2])
            if magnitude > limit:
                continue
            p = self._project(v, frame)
            if p is None:
                continue
            x, y, _k = p
            if x < -4 or y < -4 or x > width + 4 or y > height:
                continue
            strength = min(1.0, (limit - magnitude) / 1.6)
            cr.set_source_rgba(*star_tint(star[3]), 0.22 + 0.4 * strength)
            cr.arc(x, y, 0.55 + 0.35 * strength, 0, 2 * math.pi)
            cr.fill()

    def _draw_bodies(self, cr, frame, ink, targets):
        moment = self.moment
        zoom = max(1.0, (DEFAULT_FOV / self.fov) ** 0.5)
        sun = self._project(moment.sun.vector, frame) if moment.sun.altitude > -1 else None
        if sun is not None:
            x, y, _k = sun
            glow = cairo.RadialGradient(x, y, 0, x, y, 46)
            glow.add_color_stop_rgba(0, 1.0, 0.97, 0.88, 0.95)
            glow.add_color_stop_rgba(0.25, 1.0, 0.93, 0.75, 0.45)
            glow.add_color_stop_rgba(1, 1.0, 0.9, 0.7, 0.0)
            cr.set_source(glow)
            cr.arc(x, y, 46, 0, 2 * math.pi)
            cr.fill()
            cr.set_source_rgba(1.0, 0.98, 0.92, 1)
            cr.arc(x, y, 9, 0, 2 * math.pi)
            cr.fill()
            targets.append((x, y, ("body", "sun"), -27))
        for planet in moment.planets:
            p = self._project(planet.vector, frame)
            if p is None:
                continue
            x, y, _k = p
            shows = sinking(planet.vector[2])
            if shows <= 0:
                continue
            seen = planet.magnitude + min(1.6, extinction(planet.vector[2]))
            radius = max(2.4, min(5.2, 3.6 - seen * 0.55)) * zoom
            tint = PLANET_TINTS.get(planet.key, (1, 1, 1))
            cr.set_source_rgba(*tint, 0.18 * shows)
            cr.arc(x, y, radius * 2.4, 0, 2 * math.pi)
            cr.fill()
            cr.set_source_rgba(*tint, shows)
            cr.arc(x, y, radius, 0, 2 * math.pi)
            cr.fill()
            if planet.vector[2] > 0:
                targets.append((x, y, ("body", planet.key), planet.magnitude - 3))
        moon = moment.moon
        p = self._project(moon.vector, frame)
        shows = sinking(moon.vector[2] + 0.0045)      # its whole disc, not its centre
        if p is not None and shows > 0:
            x, y, k = p
            radius = max(9.0, math.radians(0.26) * k)
            if shows < 1:
                cr.push_group()
            self._draw_moon(cr, frame, x, y, radius, moon, moment.sun)
            if shows < 1:
                cr.pop_group_to_source()
                cr.paint_with_alpha(shows)
            if moon.vector[2] > 0:
                targets.append((x, y, ("body", "moon"), -20))

    def _draw_moon(self, cr, frame, x, y, radius, moon, sun):
        # The bright limb faces the Sun: find that direction on screen.
        m, s = moon.vector, sun.vector
        dot = sum(a * b for a, b in zip(m, s))
        toward = [b - dot * a for a, b in zip(m, s)]
        length = math.sqrt(sum(c * c for c in toward)) or 1.0
        step = [a + 0.02 * c / length for a, c in zip(m, toward)]
        q = self._project(step, frame)
        angle = math.atan2(q[1] - y, q[0] - x) if q else 0.0
        lit = moon.phase_fraction
        glow = cairo.RadialGradient(x, y, radius, x, y, radius * 4)
        glow.add_color_stop_rgba(0, 0.95, 0.95, 1.0, 0.10 + 0.12 * lit)
        glow.add_color_stop_rgba(1, 0.95, 0.95, 1.0, 0.0)
        cr.set_source(glow)
        cr.arc(x, y, radius * 4, 0, 2 * math.pi)
        cr.fill()
        cr.save()
        cr.translate(x, y)
        cr.rotate(angle)
        cr.set_source_rgba(0.55, 0.57, 0.62, 0.35)      # earthshine
        cr.arc(0, 0, radius, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgba(0.98, 0.97, 0.92, 1)
        # Lit half toward +x, then the terminator as a half-ellipse.
        cr.arc(0, 0, radius, -math.pi / 2, math.pi / 2)
        bulge = 2 * lit - 1            # -1 new, 0 half, 1 full
        cr.save()
        cr.scale(bulge if abs(bulge) > 0.01 else 0.01, 1)
        cr.arc(0, 0, radius, math.pi / 2, 3 * math.pi / 2)
        cr.restore()
        cr.close_path()
        cr.fill()
        cr.restore()

    def _draw_ground(self, cr, frame, width, height):
        """The horizon as it looks at night: no edge and no dark land, just the air's light.

        The sky brightens into a glow along the horizon (the light of the air and of
        far-off towns), the stars dim into it, and below it there is only a soft haze.
        In this projection the horizon is a circle, so the glow follows its curve.
        """
        points = []
        for offset in (0, 90, -90):
            p = self._project(sky.horizontal(self.azimuth + offset, 0), frame)
            if p is None:
                return
            points.append(p[:2])
        center, radius = _circle(*points)
        if center is None:      # looking straight along the horizon: it is a line
            return
        cx, cy = center
        if self.high_contrast:      # a crisp line, not a glow
            ink = self._color("luma_sky_card_ink")
            cr.set_source_rgba(*ink[:3], 0.9)
            cr.set_line_width(1.5)
            cr.arc(cx, cy, radius, 0, 2 * math.pi)
            cr.stroke()
            return
        stops = self._sky_stops(self.moment.sun.altitude)
        glow = _mix(stops[2][:3], self._color("luma_sky_card_ink")[:3], 0.18)
        up = max(70.0, height * 0.26)        # how high the glow climbs
        down = max(36.0, height * 0.08)      # where the haze below settles
        inner = max(1.0, radius - up)
        outer = radius + down
        light = cairo.RadialGradient(cx, cy, inner, cx, cy, outer)
        at = lambda r: (r - inner) / (outer - inner)
        light.add_color_stop_rgba(0, *glow, 0.0)
        light.add_color_stop_rgba(at(radius - up * 0.5), *glow, 0.07)
        light.add_color_stop_rgba(at(radius - up * 0.15), *glow, 0.22)
        light.add_color_stop_rgba(at(radius), *glow, 0.36)      # brightest along the horizon itself
        light.add_color_stop_rgba(1, *glow, 0.26)               # a haze below, never darker than the sky
        light.set_extend(cairo.EXTEND_PAD)
        # Only outside the glow's inner edge is painted: a whole-window gradient costs a core here.
        cr.save()
        cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        cr.rectangle(0, 0, width, height)
        cr.new_sub_path()
        cr.arc(cx, cy, inner, 0, 2 * math.pi)
        cr.set_source(light)
        cr.fill()
        cr.restore()
        # A grain of a colour step or two over the gradients, so smooth twilight shows no bands.
        cr.set_source(_dither())
        cr.paint()

    def _draw_labels(self, cr, frame, ink, limit, width, height):
        # Most important first; a label that would overlap one already placed, or what floats over
        # the sky (the compass, the corner), is left out, or for a planet moved to another side.
        placed = [tuple(box) for box in self.reserved()]
        self._bounds = (width, height)
        bodies = [self.moment.moon, *sorted(self.moment.planets, key=lambda planet: planet.magnitude)]
        if self.moment.sun.altitude > -1:
            bodies.insert(0, self.moment.sun)
        for body in bodies:
            if body.altitude < 0 or (body.key in ("uranus", "neptune") and self.fov > 40):
                continue
            p = self._project(body.vector, frame)
            if p is None or not (0 < p[0] < width and 0 < p[1] < height):
                continue
            offset = 16 if body.key == "moon" else 9
            for dx, dy, align in ((offset, -offset, "left"), (offset, offset, "left"),
                                  (-offset, offset, "right"), (-offset, -offset, "right")):
                if self._text(cr, body.name, p[0] + dx, p[1] + dy, ink, role="caption", alpha=0.95, align=align,
                              weight=Pango.Weight.SEMIBOLD, placed=placed):
                    break
        name_limit = 1.6 + max(0.0, (100 - self.fov) / 30)
        named = sorted((self.catalog.stars[index][2], index, label) for index, label in self.catalog.names.items()
                       if "n" in label)
        for magnitude, index, label in named:
            if magnitude > min(name_limit, limit - 0.5):
                break
            v = self._stars_h[index]
            if v[2] < 0.03 or magnitude + extinction(v[2]) > limit - 0.5:
                continue
            p = self._project(v, frame)
            if p is None or not (0 < p[0] < width and 0 < p[1] < height):
                continue
            # Above and to the right, or the first other side that is free (under the compass, say).
            for dx, dy, align in ((7, -7, "left"), (7, 7, "left"), (-7, 7, "right"), (-7, -7, "right")):
                if self._text(cr, label["n"], p[0] + dx, p[1] + dy, ink, role="caption",
                              alpha=1.0 if self.high_contrast else 0.7, align=align, placed=placed):
                    break
        if self.show_figures:
            for entry in self.catalog.constellations.values():
                if entry["rank"] > (1 if self.fov > 100 else 2 if self.fov > 50 else 3):
                    continue
                v = self.moment.to_horizontal(sky.unit(entry["ra"], entry["dec"]))
                if v[2] < 0.05:
                    continue
                p = self._project(v, frame)
                if p is None or not (0 < p[0] < width and 0 < p[1] < height):
                    continue
                self._text(cr, entry["name"], p[0], p[1], ink, role="caption", alpha=1.0 if self.high_contrast else 0.55, align="center",
                           placed=placed)

    def _draw_selection(self, cr, frame):
        cr.new_path()
        vector = self.vector_of(self.selection)
        if vector is None:
            return
        p = self._project(vector, frame)
        if p is None:
            return
        accent = self._color("luma_accent", "luma_sky_card_ink")
        radius = 18 if not (self.selection[0] == "body" and self.selection[1] == "moon") else 24
        cr.set_source_rgba(accent[0], accent[1], accent[2], 0.95)
        cr.set_line_width(2.0)
        cr.arc(p[0], p[1], radius, 0, 2 * math.pi)
        cr.stroke()

    def _text(self, cr, text, x, y, ink, *, role="caption", alpha=1.0, align="left", weight=None, placed=None):
        cr.new_path()
        layout = PangoCairo.create_layout(cr)
        font = type_font(role) if type_font else Pango.FontDescription.from_string("Sans 9")
        if weight is not None:
            font = font.copy()
            font.set_weight(weight)
        layout.set_font_description(font)
        layout.set_text(text, -1)
        _ink, logical = layout.get_pixel_extents()
        w, h = logical.width, logical.height
        if align == "center":
            x, y = x - w / 2, y - h / 2
        elif align == "top":
            x = x - w / 2
        elif align == "right":
            x, y = x - w, y - h / 2
        else:
            y = y - h / 2
        if placed is not None:
            box = (x - 3, y - 1, x + w + 3, y + h + 1)
            width, height = getattr(self, "_bounds", (1e9, 1e9))
            if box[0] < 0 or box[1] < self.top_inset or box[2] > width or box[3] > height:
                return False
            if any(box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in placed):
                return False
            placed.append(box)
        cr.move_to(x, y)
        cr.set_source_rgba(ink[0], ink[1], ink[2], ink[3] * alpha)
        PangoCairo.show_layout(cr, layout)
        cr.new_path()
        return True

    # ── input ─────────────────────────────────────────────────────────

    def _degrees_per_pixel(self):
        _f, _r, _u, scale, _cx, _cy = self._frame(self.get_width(), self.get_height())
        return math.degrees(2 / scale)

    def _drag_begin(self, _gesture, _x, _y):
        self._drag_start = (self.azimuth, self.altitude)
        self._moved = False
        if self._animation:
            self.remove_tick_callback(self._animation)
            self._animation = 0

    def _drag_update(self, _gesture, dx, dy):
        if self._drag_start is None:
            return
        if abs(dx) + abs(dy) > 6:
            self._moved = True
        if not self._moved:
            return
        step = self._degrees_per_pixel()
        self.azimuth = (self._drag_start[0] - dx * step) % 360
        self.altitude = self._clamp_altitude(self._drag_start[1] + dy * step)
        self._changed()

    def _drag_end(self, _gesture, _dx, _dy):
        self._drag_start = None

    def _zoomed(self, _gesture, scale):
        if self._zoom_start:
            self.fov = self._clamp_fov(self._zoom_start / max(scale, 0.05))
            self.altitude = self._clamp_altitude(self.altitude)
            self._moved = True
            self._changed()

    def _scrolled(self, _controller, _dx, dy):
        self.zoom_by(1.12 ** dy)
        return True

    def _released(self, _gesture, n_press, x, y):
        self.grab_focus()
        if self._moved or n_press != 1:
            return
        best, best_score = None, None
        reach = 26
        for tx, ty, selection, magnitude in self._targets:
            distance = math.hypot(tx - x, ty - y)
            if distance > reach:
                continue
            score = distance + magnitude * 2.5
            if best_score is None or score < best_score:
                best, best_score = selection, score
        self.emit("picked", best)

    def _key(self, _controller, keyval, _code, _state):
        from gi.repository import Gdk
        step = max(2.0, self.fov / 12)
        if keyval == Gdk.KEY_Left:
            self.look(self.azimuth - step, self.altitude, animate=False)
        elif keyval == Gdk.KEY_Right:
            self.look(self.azimuth + step, self.altitude, animate=False)
        elif keyval == Gdk.KEY_Up:
            self.look(self.azimuth, self.altitude + step, animate=False)
        elif keyval == Gdk.KEY_Down:
            self.look(self.azimuth, self.altitude - step, animate=False)
        elif keyval in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
            self.zoom_by(1 / 1.25)
        elif keyval in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            self.zoom_by(1.25)
        elif keyval == Gdk.KEY_Escape and self.selection is not None:
            self.emit("picked", None)
        else:
            return False
        return True


def _mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def _circle(a, b, c):
    """The circle through three points, or (None, None) when they are in a line."""
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-6:
        return None, None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    return (ux, uy), math.hypot(ax - ux, ay - uy)



# How much each of the Milky Way's five outline levels glows: steep, so the core reads and the edges fade.
BRIGHTNESS = (0, 0.45, 1.26, 2.32, 3.58, 5.0)


def _read_high_contrast() -> bool:
    try:
        return bool(Adw and Adw.StyleManager.get_default().get_high_contrast())
    except Exception:  # noqa: BLE001 - no display, as in previews
        return False


_DITHER = []


def _dither() -> cairo.SurfacePattern:
    """A tiled, fixed noise of ±1–3 colour steps: breaks the steps an 8-bit gradient shows."""
    if not _DITHER:
        size = 64
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
        stride = surface.get_stride()
        pixels = bytearray(stride * size)
        rng = random.Random(29)
        for y in range(size):
            for x in range(size):
                alpha = rng.randint(1, 3)
                level = alpha if rng.random() < 0.5 else 0       # premultiplied white, or black
                i = y * stride + x * 4
                pixels[i:i + 4] = bytes((level, level, level, alpha))
        surface.get_data()[:] = pixels
        surface.mark_dirty()
        pattern = cairo.SurfacePattern(surface)
        pattern.set_extend(cairo.EXTEND_REPEAT)
        _DITHER.append(pattern)
    return _DITHER[0]


def _milky_dust(catalog):
    """Grains scattered through the Milky Way's cells, more where it is brighter, and a patchiness for
    its glow. Seeded, so the sky looks the same every night."""
    rng = random.Random(1781)
    per_level = (0, 0.6, 3, 6, 10, 14)
    vectors, strengths = [], []
    for ra, dec, level in catalog.milky_way:
        count = per_level[level]
        whole = int(count) + (1 if rng.random() < count - int(count) else 0)
        stretch = 1 / max(0.2, math.cos(math.radians(dec)))
        for _ in range(whole):
            vectors.append(sky.unit(ra + rng.uniform(-0.75, 0.75) * stretch, dec + rng.uniform(-0.75, 0.75)))
            strengths.append(min(0.99, level / 5 * rng.uniform(0.35, 1.1)))
    patches = [rng.uniform(0.8, 1.2) for _ in catalog.milky_way]
    return vectors, strengths, patches


def _box_blur(surface: cairo.ImageSurface) -> cairo.ImageSurface:
    """A 3x3 box blur by stacking offset copies; the surface is small, so this is quick."""
    w, h = surface.get_width(), surface.get_height()
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(out)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            cr.set_source_surface(surface, dx, dy)
            cr.paint_with_alpha(1 / 9)
    return out


def extinction(z: float) -> float:
    """Magnitudes lost to the air at height z (the sine of altitude), for a clear rural sky.

    Stars fade as they near the horizon, as they do through that much air; capped, so the
    brightest still reach it. Below it they sink out of sight within a few degrees.
    """
    if z < 0:
        return 3.0 + -z * 90
    airmass = 1.0 / (z + 0.025 * math.exp(-11.0 * z))
    return min(3.0, 0.28 * (airmass - 1.0))


def sinking(z: float) -> float:
    """How much of something still shows as it goes below the horizon: gone two degrees down."""
    return 1.0 if z >= 0 else max(0.0, 1.0 + z / 0.035)

