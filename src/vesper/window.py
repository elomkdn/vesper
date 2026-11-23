# SPDX-License-Identifier: GPL-3.0-or-later
"""Vesper's window: the sky in one island, the bar for time, tonight and finding things."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from luma_appkit import (
    ActionCenter, AppWindow, BarAction, BarChip, Command, CommandGroup, CommandRegistry, CornerPill,
    DetailsPane, EmptyState, FactRow, IconOnlyButton, Island, PanelChoices, PanelField, PanelHeading, PanelRow, SPACER, Toast,
    ToastHost, panel_list,
)
try:
    from luma_appkit import Sparkline
except ImportError:  # pragma: no cover - older toolkits
    Sparkline = None

from . import astronomy as ae
from . import places, sky
from .compass import Compass
from .locate import Locator
from .skyview import SkyView
from . import style
from .wheel import TimeWheels

APP_ID = "io.github.elomkdn.Vesper"
PHONE_MAX = 559


def data_dir() -> Path:
    for candidate in (os.environ.get("VESPER_DATA"), "/app/share/vesper",
                      Path(__file__).resolve().parents[2] / "data"):
        if candidate and (Path(candidate) / "sky.json").exists():
            return Path(candidate)
    raise FileNotFoundError("Vesper's sky catalogue is missing")


def _when_words(moment_at: datetime, now: datetime, zone=None) -> str:
    local, today = moment_at.astimezone(zone), now.astimezone(zone)
    days = (local.date() - today.date()).days
    clock = local.strftime("%H:%M")
    if days == 0:
        return f"Today {clock}"
    if days == 1:
        return f"Tomorrow {clock}"
    if days == -1:
        return f"Yesterday {clock}"
    return local.strftime("%a %d %b ") + clock


class VesperWindow(AppWindow):
    def __init__(self, application):
        folder = data_dir()
        self.catalog = sky.Catalog.load(folder / "sky.json")
        self.cities = places.Cities(folder / "cities.json")
        self.offset = timedelta(0)
        self.selection = None
        self.phone = False
        self._tonight = []
        self._tonight_for = None
        self._find_results = []
        self._live_source = 0
        self._bar_stale = False      # the bar waits for a grown panel to fold
        self._time_sync = None       # updates the open Time panel
        self._scrub_pending = False
        self._night_for = None
        self._night_jumps = {}
        groups = (
            CommandGroup("", (
                Command("sky.now", "Back to now", self.back_to_now, "rotate-ccw", shortcut=("", "N")),
                Command("sky.tonight", "Tonight", self.open_tonight, "moon", shortcut=("", "T")),
                Command("sky.time", "Change time", self.open_time, "clock", shortcut=("", "H")),
                Command("sky.find", "Find in the sky", self.open_find, "search", shortcut=("Ctrl", "F")),
                Command("sky.location", "Change location…", self.open_location, "map-pin", shortcut=("Ctrl", "L")),
            )),
            self._view_group(),
            CommandGroup("", (Command("sky.quit", "Quit Vesper", self.close, "log-out", shortcut=("Ctrl", "Q")),)),
        )
        commands = CommandRegistry(groups)
        # The single-letter keys (N, T, H, C, L, M, K), as LumaUI registers them.
        self._letter_keys = [(command.id.replace(".", "-"), "".join(command.shortcut))
                             for group in groups for command in group.commands
                             if command.shortcut and not command.shortcut[0]]
        self._letters_on = True
        super().__init__(application=application, app_id=APP_ID, title="Vesper", icon_name=APP_ID,
                         commands=commands, default_width=1180, default_height=760,
                         minimum_width=360, minimum_height=420)

        self.view = SkyView(self.catalog)
        self.view.set_options(figures=bool(self.recall("figures", True)), labels=bool(self.recall("labels", True)),
                              milky_way=bool(self.recall("milky_way", True)))
        look = self.recall("look")
        if isinstance(look, list) and len(look) == 3:
            # Keep where you were facing and how far you'd zoomed; the horizon always opens low.
            self.view.azimuth = float(look[0]) % 360
            self.view.fov = max(30.0, min(130.0, float(look[2])))
        self.view.frame_horizon = True
        self.view.connect("picked", lambda _v, selection: self.select(selection))
        self.view.connect("view-changed", lambda _v: self._view_changed())

        self.details = DetailsPane("Details", closable=True, on_close=self._details_closed)
        # Top right, a rail down the edge: what the sky shows, each one click away and always in sight,
        # then Information. (The same switches are in the app menu, with their keys.)
        self.corner = CornerPill(states=(
            ("sparkles", "Show constellations", self.view.show_figures, self.set_figures),
            ("type", "Show names", self.view.show_labels, self.set_labels),
            ("waves", "Show the Milky Way", self.view.show_milky_way, self.set_milky_way),
            ("compass", "Show compass", bool(self.recall("compass", True)), self.set_compass),
        ), info=self.details, orientation="vertical")
        self.corner.set_margin_top(12)
        self.corner.set_margin_end(12)
        self.compass = Compass(self.view, on_pick=self._go_to)
        self.compass.set_margin_top(14)
        self.compass.set_visible(bool(self.recall("compass", True)))
        overlay = Gtk.Overlay(child=self.view)
        overlay.add_overlay(self.compass)
        overlay.add_overlay(self.corner)

        self.empty = EmptyState("No location yet", "Vesper shows the sky above you. Use your location, "
                                "or choose your city.", "lumaui-map-pin-symbolic",
                                primary=("Use my location", self.use_my_location),
                                secondary=("Choose a city", self.open_location))
        self.stack = Gtk.Stack(hexpand=True, vexpand=True)
        self.stack.add_named(overlay, "sky")
        self.stack.add_named(self.empty, "empty")

        self.island = Island()
        self.island.set_hexpand(True)
        self.island.append(self.stack)
        self.host = ToastHost(self.island)
        body = Gtk.Box(hexpand=True, vexpand=True)
        body.append(self.host)
        body.append(self.details)
        self.set_body(body)
        self.set_phone_bleed(True)
        self.view.bottom_inset = 84

        self.center = ActionCenter()
        self.center.attach(self.host)
        self.center.connect("panel-changed", self._panel_changed)
        self.connect("notify::focus-widget", self._focus_moved)
        self.view.reserved = self._reserved_areas
        style.install()

        phone = Adw.Breakpoint.new(Adw.BreakpointCondition.parse(f"max-width: {PHONE_MAX}px"))
        phone.add_setter(self.corner, "visible", False)
        phone.connect("apply", lambda _b: self._set_phone(True))
        phone.connect("unapply", lambda _b: self._set_phone(False))
        self.add_breakpoint(phone)
        self.connect("close-request", self._closing)

        self.place = places.Place.from_saved(self.recall("place"))
        if os.environ.get("VESPER_PLACE"):          # development and check runs
            found = self.cities.search(os.environ["VESPER_PLACE"])
            self.place = found[0] if found else self.place
        if os.environ.get("VESPER_TIME"):
            self.offset = datetime.fromisoformat(os.environ["VESPER_TIME"]) - self.now()
        self._show_place()
        self._live_source = GLib.timeout_add_seconds(30, self._tick)
        # Quiet at rest: while the window is hidden nothing is drawn, so the live sky need not keep time.
        if self.find_property("suspended") is not None:
            self.connect("notify::suspended", self._suspended_changed)

    # ── time and place ────────────────────────────────────────────────

    @property
    def zone(self):
        return self.place.tzinfo if self.place is not None else None

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def when(self) -> datetime:
        return self.now() if self.pinned is None else self.pinned

    # The moment shown is now, or a moment someone chose, which then stays put as the clock runs on.
    @property
    def offset(self) -> timedelta:
        pinned = getattr(self, "pinned", None)
        return timedelta(0) if pinned is None else pinned - self.now()

    @offset.setter
    def offset(self, value: timedelta) -> None:
        self.pinned = None if value == timedelta(0) else self.now() + value

    def _show_place(self) -> None:
        if self.place is None:
            self.stack.set_visible_child_name("empty")
            self.center.hide_bar()
            return
        self.stack.set_visible_child_name("sky")
        self._night_if_light()
        self.refresh()

    def _night_if_light(self) -> None:
        """Vesper opens on stars: in daylight or bright twilight it moves to tonight, with Undo."""
        if self.place is None or self.offset != timedelta(0) or os.environ.get("VESPER_TIME"):
            return
        now = self.now()
        moment = sky.moment(now, self.place.latitude, self.place.longitude)
        if moment.sun.altitude <= -10:
            return
        dark = sky.next_dark(now, self.place.latitude, self.place.longitude)
        if dark is None:        # the midnight sun: it doesn't get dark, so the sky stays on now
            return
        dark += timedelta(minutes=40)
        self.offset = dark - now
        words = dark.astimezone(self.zone).strftime("%H:%M")
        GLib.idle_add(lambda: Toast.show(self.host, f"Moved to {words}, once it's dark", kind="done",
                                         undo=self.back_to_now) and False)

    def refresh(self) -> None:
        if self.place is None:
            return
        self.view.set_moment(sky.moment(self.when(), self.place.latitude, self.place.longitude))
        self.compass.queue_draw()
        if self.selection is not None and self.details.shown:
            self._fill_details()
        self._sync_bar()

    def _sync_bar(self) -> None:
        """A new bar would fold an open panel, so while one is open only the time's words change."""
        if self.center.grown is not None and self.selection is None and getattr(self, "_time_action", None):
            child = self._bar_widget(self._time_action)
            words = getattr(getattr(child, "bar_button", child), "bar_dropdown_words", None)
            if words is not None:
                words.set_label(self._time_words())
            self._bar_stale = True
            if self.center.grown == "time" and self._time_sync is not None:
                self._time_sync()
            return
        self.show_bar()

    def _panel_changed(self, _center, key: str) -> None:
        if key != "time":
            self._time_sync = None
        if not key and self._bar_stale:
            self._bar_stale = False
            GLib.idle_add(lambda: self.show_bar() and False)

    def _focus_moved(self, *_args) -> None:
        """GTK hears application shortcuts before the focused widget, so a bare-letter shortcut would
        swallow that letter in Find or the city search ("saturn" would open Tonight at its "t").
        While a field has focus the letter keys step aside; Ctrl shortcuts stay."""
        typing = isinstance(self.get_focus(), Gtk.Editable)
        application = self.get_application()
        if application is None or typing != self._letters_on:
            return
        self._letters_on = not typing
        for name, key in self._letter_keys:
            application.set_accels_for_action(f"app.{name}", [] if typing else [key])

    def _reserved_areas(self) -> list:
        """What floats over the sky, in the sky's coordinates, so its names keep clear of it."""
        areas = []
        for widget in (getattr(self, "compass", None), getattr(self, "corner", None)):
            if widget is None or not widget.get_visible() or not widget.get_mapped():
                continue
            ok, rect = widget.compute_bounds(self.view)
            if ok:
                x, y = rect.get_x(), rect.get_y()
                areas.append((x - 4, y - 2, x + rect.get_width() + 4, y + rect.get_height() + 2))
        return areas

    def _time_words(self) -> str:
        """Short enough for a phone's bar: "21:30" tonight, "Tue 21:30" on another night."""
        if self.offset == timedelta(0):
            return "Now"
        when, now = self.when(), self.now()
        local = when.astimezone(self.zone)
        if sky.day_start(when, self.zone) == sky.day_start(now + timedelta(hours=6), self.zone):
            return local.strftime("%H:%M")
        return local.strftime("%a %H:%M")

    def _suspended_changed(self, *_args) -> None:
        if self.get_property("suspended"):
            if self._live_source:
                GLib.source_remove(self._live_source)
                self._live_source = 0
        elif not self._live_source:
            self._live_source = GLib.timeout_add_seconds(30, self._tick)
            self._tick()        # catch up with the sky at once

    def _tick(self):
        if self.place is not None and self.offset == timedelta(0) and self.center.grown is None:
            self.refresh()
        return GLib.SOURCE_CONTINUE

    def set_place(self, place: places.Place) -> None:
        self.place = place
        self.remember("place", place.saved())
        self._tonight_for = None
        light = self.offset == timedelta(0) and sky.moment(
            self.now(), place.latitude, place.longitude).sun.altitude > -10
        self._show_place()
        if not light:
            Toast.show(self.host, f"Location set to {place.name}", kind="place")

    def set_offset(self, offset: timedelta, *, refresh: bool = True) -> None:
        self.offset = offset
        if refresh:
            self.refresh()

    def back_to_now(self) -> None:
        if self.center.grown is not None:
            self.center.fold()
        self.set_offset(timedelta(0))

    # ── view options ──────────────────────────────────────────────────

    def _view_group(self) -> CommandGroup:
        view = lambda: getattr(self, "view", None)
        return CommandGroup("Show", (
            Command("sky.figures", "Show constellations", lambda: self.set_figures(not self.view.show_figures),
                    "sparkles", shortcut=("", "C"), checked=lambda: getattr(view(), "show_figures", True)),
            Command("sky.labels", "Show names", lambda: self.set_labels(not self.view.show_labels),
                    "type", shortcut=("", "L"), checked=lambda: getattr(view(), "show_labels", True)),
            Command("sky.milkyway", "Show the Milky Way", lambda: self.set_milky_way(not self.view.show_milky_way),
                    "waves", shortcut=("", "M"), checked=lambda: getattr(view(), "show_milky_way", True)),
            Command("sky.compass", "Show compass", lambda: self.set_compass(not self.compass.get_visible()),
                    "compass", shortcut=("", "K"),
                    checked=lambda: getattr(self, "compass", None) is None or self.compass.get_visible()),
        ))

    def set_milky_way(self, on: bool) -> None:
        self.view.set_options(milky_way=on)
        self.remember("milky_way", on)
        self._show_switch(2, on)

    def set_compass(self, on: bool) -> None:
        self.compass.set_visible(on)
        self.remember("compass", on)
        self._show_switch(3, on)

    def _show_switch(self, index: int, on: bool) -> None:
        """Keep the corner's switch in step when a key or a menu changed the view."""
        corner = getattr(self, "corner", None)
        button = corner.controls.get(f"states.{index}") if corner is not None else None
        if button is not None and button.get_active() != on:
            button.set_active(on)

    def set_figures(self, on: bool) -> None:
        self.view.set_options(figures=on)
        self.remember("figures", on)
        self._show_switch(0, on)

    def set_labels(self, on: bool) -> None:
        self.view.set_options(labels=on)
        self.remember("labels", on)
        self._show_switch(1, on)

    def _view_changed(self) -> None:
        self._remember_look()

    def _remember_look(self) -> None:
        self.remember("look", [round(self.view.azimuth, 1), round(self.view.altitude, 1), round(self.view.fov, 1)])

    def _set_phone(self, phone: bool) -> None:
        self.phone = phone
        self.view.top_inset = self.status_inset if phone else 0
        # On a phone the corner pill steps aside, so the compass takes the width.
        self.compass.set_side_room(16 if phone else 84)
        self.compass.set_margin_top((self.status_inset + 8) if phone else 14)
        self.view.queue_draw()
        self.show_bar()

    # ── the bar ───────────────────────────────────────────────────────

    def show_bar(self) -> None:
        if self.place is None:
            self.center.hide_bar()
            return
        if self.selection is not None:
            name = self.name_of(self.selection)
            items = [BarChip(name, on_dismiss=lambda: self.select(None)),
                     BarAction("scan-eye", tooltip=f"Look at {name}",
                               on_activate=lambda: self.view.look_at(self.selection))]
            if self.phone:      # on a computer, Information is the corner's
                items.append(BarAction("info", tooltip="Information", active=self.details.shown,
                                       on_activate=self.toggle_details))
            self.center.show_bar(items)
            return
        self._bar_stale = False
        time_words = self._time_words()
        more = [BarAction("map-pin", "Change location…", on_activate=self.open_location)]
        if self.offset != timedelta(0):
            more.insert(0, BarAction("rotate-ccw", "Back to now", on_activate=self.back_to_now))
        if self.phone:      # the corner steps aside on a phone, so its choices come here
            more += [BarAction("sparkles", "Show constellations", active=self.view.show_figures,
                               on_activate=lambda: (self.set_figures(not self.view.show_figures), self.show_bar())),
                     BarAction("type", "Show names", active=self.view.show_labels,
                               on_activate=lambda: (self.set_labels(not self.view.show_labels), self.show_bar())),
                     BarAction("waves", "Show the Milky Way", active=self.view.show_milky_way,
                               on_activate=lambda: (self.set_milky_way(not self.view.show_milky_way), self.show_bar())),
                     BarAction("compass", "Show compass", active=self.compass.get_visible(),
                               on_activate=lambda: (self.set_compass(not self.compass.get_visible()), self.show_bar()))]
        # Time: the moment shown, as a picker you tap (Tasks' "Today ⌄"); it opens the wheels.
        self._time_action = BarAction("", time_words, tooltip="Change time", dropdown=True,
                                      panel=self._time_panel, key="time")
        self._tonight_action = BarAction("moon", "Tonight", primary=True, panel=self._tonight_panel, key="tonight")
        self.center.show_bar([self._time_action, SPACER,
                              BarAction("search", tooltip="Find in the sky", on_activate=self.open_find),
                              self._tonight_action], more=more)

    def _bar_widget(self, item):
        child = self.center.bar_row.get_first_child()
        while child is not None:
            if getattr(child, "bar_item", None) is item:
                return child
            child = child.get_next_sibling()
        return self.center

    # Time travel: hour and minutes on wheels like an alarm's, the night's moments a tap away,
    # and the nights before and after.
    def _time_panel(self):
        title = PanelHeading("")
        title.set_hexpand(True)
        heading = title.label
        header = Gtk.Box(valign=Gtk.Align.CENTER)
        header.append(title)
        for icon, words, days in (("chevron-left", "Night before", -1), ("chevron-right", "Night after", 1)):
            header.append(IconOnlyButton(icon, words, size="row",
                                         on_click=lambda d=days: self.set_offset(self.offset + timedelta(days=d))))
        shown = {"start": None}

        def turned(minutes):
            if shown["start"] is not None:
                self._scrub(shown["start"] + timedelta(minutes=minutes))

        wheels = TimeWheels([f"{h:02d}" for h in range(12, 24)] + [f"{h:02d}" for h in range(12)], turned)

        def jump(key):
            target = self.now() if key == "now" else self._night_jumps.get(key)
            if target is not None:
                self.set_offset(target - self.now())

        choices = PanelChoices((("now", "Now"), ("dusk", "Dusk"), ("midnight", "Midnight"), ("dawn", "Dawn")),
                               selected="", on_choose=jump)

        def sync():
            when = self.when()
            start = sky.day_start(when, self.zone)
            heading.set_label(self._night_words(start))
            if shown["start"] != start:
                shown["start"] = start
                # Real clock hours from that noon, so a clock change night reads right.
                wheels.set_hour_names([(start + timedelta(hours=h)).astimezone(self.zone).strftime("%H")
                                       for h in range(24)])
            night = (self.place.latitude, self.place.longitude, start)
            if self._night_for != night:
                self._night_for = night
                sunset, sunrise = sky.night_window(start + timedelta(hours=1), self.place.latitude,
                                                   self.place.longitude, self.zone)
                self._night_jumps = {"dusk": sunset + timedelta(minutes=30), "dawn": sunrise - timedelta(hours=1),
                                     "midnight": start + timedelta(hours=12)}
            wheels.show((when - start).total_seconds() / 60)
            picked = "now" if self.offset == timedelta(0) else next(
                (key for key, at in self._night_jumps.items() if abs((at - when).total_seconds()) < 150), "")
            choices.set_selected(picked)

        self._time_sync = sync
        self._time_wheels = wheels
        sync()
        return panel_list([header, wheels, choices], label="Time")

    def _night_words(self, start: datetime) -> str:
        """Which night the wheels are on, by its dates: "Mon 23 → Tue 24 Nov"."""
        evening = start.astimezone(self.zone)
        morning = (start + timedelta(hours=24)).astimezone(self.zone)
        first = f"{evening:%a} {evening.day}" + ("" if evening.month == morning.month else f" {evening:%b}")
        return f"{first} → {morning:%a} {morning.day} {morning:%b}"

    def _scrub(self, when: datetime) -> None:
        """A wheel turned: set the time now, redraw the sky once the frame is free."""
        self.offset = when - self.now()
        if not self._scrub_pending:
            self._scrub_pending = True
            GLib.idle_add(self._scrub_apply)

    def _scrub_apply(self):
        self._scrub_pending = False
        self.refresh()
        return False

    # What's worth seeing tonight; a row takes you there.
    def _tonight_panel(self):
        key = (self.place.latitude, self.place.longitude, self.now().astimezone(self.zone).date())
        if self._tonight_for != key:
            self._tonight = sky.tonight(self.now(), self.place.latitude, self.place.longitude, self.zone)
            self._tonight_for = key
        rows = [PanelHeading(f"Tonight over {self.place.name}")]
        for highlight in self._tonight:
            rows.append(PanelRow(highlight.title, icon=highlight.icon, subtitle=highlight.detail,
                                 detail=highlight.time or None,
                                 on_activate=lambda h=highlight: self.go_to_highlight(h)))
        return panel_list(rows, label="Tonight")

    def open_time(self) -> None:
        if self.place is not None and self.selection is None:
            self.center.grow("time", self._time_panel(), anchor=self._bar_widget(self._time_action))

    def open_tonight(self) -> None:
        if self.place is not None and self.selection is None:
            self.center.grow("tonight", self._tonight_panel(), anchor=self._bar_widget(self._tonight_action))

    def go_to_highlight(self, highlight: sky.Highlight) -> None:
        if highlight.best is not None:
            self.set_offset(highlight.best - self.now())
        if highlight.key not in ("dark",):
            self.select(("body", highlight.key))
            self.view.look_at(("body", highlight.key))

    # Find: the bar becomes the field, matches grow above it.
    def open_find(self) -> None:
        if self.place is None:
            return
        if self.center.grown is not None:
            self.center.fold()
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        panel.append(PanelHeading("Find in the sky"))
        self._find_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        panel.append(self._find_list)
        field = PanelField("search", "A star, planet or constellation", on_change=self._find_changed,
                           on_submit=lambda _text: self._find_pick())
        self._find_changed("")
        self.center.grow("find", panel, entry=field, close_word="Cancel")

    def _find_changed(self, text: str) -> None:
        self._find_results = self.search(text)
        child = self._find_list.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self._find_list.remove(child)
            child = following
        for selection, title, subtitle, icon in self._find_results[:7]:
            self._find_list.append(PanelRow(title, icon=icon, subtitle=subtitle,
                                            on_activate=lambda s=selection: self._go_to(s)))
        if text and not self._find_results:
            self._find_list.append(PanelHeading("Nothing by that name"))

    def _find_pick(self) -> None:
        if self._find_results:
            self._go_to(self._find_results[0][0])

    def _go_to(self, selection) -> None:
        if self.center.grown is not None:
            self.center.fold()
        self.select(selection)
        self.view.look_at(selection)
        vector = self.view.vector_of(selection)
        if vector is not None and vector[2] < 0:
            Toast.show(self.host, f"{self.name_of(selection)} is below the horizon now", kind="warning")

    def search(self, text: str) -> list[tuple]:
        moment = self.view.moment
        query = text.strip().casefold()
        found = []
        bodies = [moment.moon, *moment.planets[:5], moment.sun] if moment else []
        if not query:
            for body in bodies:
                if body.altitude > 0:
                    found.append((("body", body.key), body.name, self.where_words(body.vector), self.icon_of(body.key)))
            return found
        for body in [*bodies, *(moment.planets[5:] if moment else [])]:
            if body.name.casefold().startswith(query):
                found.append((("body", body.key), body.name, self.where_words(body.vector), self.icon_of(body.key)))
        for key, entry in self.catalog.constellations.items():
            if entry["name"].casefold().startswith(query):
                found.append((("constellation", key), entry["name"], "Constellation", "sparkles"))
        starts, contains = [], []
        for index, label in self.catalog.names.items():
            name = label.get("n", "")
            if not name:
                continue
            folded = name.casefold()
            if folded.startswith(query) or query in folded:
                vector = self.view._stars_h[index] if self.view._stars_h else None
                row = (("star", index), name, f"Star in {self._constellation(label)}" if vector is None
                       else f"Star in {self._constellation(label)} · {self.where_words(vector, short=True)}", "star")
                (starts if folded.startswith(query) else contains).append((self.catalog.stars[index][2], row))
        found += [row for _m, row in sorted(starts, key=lambda item: item[0])]
        found += [row for _m, row in sorted(contains, key=lambda item: item[0])]
        return found

    # Location: your position, or a city typed in the bar.
    def open_location(self) -> None:
        if self.center.grown is not None:
            self.center.fold()
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        panel.append(PanelHeading("Where you look from"))
        self._city_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        panel.append(self._city_list)
        self._city_results = []
        field = PanelField("map-pin", "City, or latitude and longitude", on_change=self._city_changed,
                           on_submit=lambda _text: self._city_pick())
        self._city_changed("")
        if self.place is None:
            self.center.show_bar([BarAction("map-pin", "Choose a city", primary=True, on_activate=self.open_location)])
        self.center.grow("location", panel, entry=field, close_word="Cancel")

    def _city_changed(self, text: str) -> None:
        self._city_results = self.cities.search(text)
        child = self._city_list.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self._city_list.remove(child)
            child = following
        if not text.strip():
            self._city_list.append(PanelRow("Use my location", icon="navigation",
                                            subtitle="Asks the system, only this once",
                                            on_activate=self.use_my_location))
        if not text.strip() and self.place is not None:
            self._city_list.append(PanelRow(self.place.name, icon="map-pin", subtitle=self.place.region, current=True,
                                            closes=False))
        for place in self._city_results[:6]:
            self._city_list.append(PanelRow(place.name, icon="map-pin", subtitle=place.region,
                                            on_activate=lambda p=place: self._choose_city(p)))
        if text.strip() and not self._city_results:
            self._city_list.append(PanelHeading("No city by that name"))

    def _city_pick(self) -> None:
        if self._city_results:
            self._choose_city(self._city_results[0])

    def use_my_location(self) -> None:
        """Ask the Location portal once; the nearest bundled city names the place and gives its time zone."""
        if self.center.grown is not None:
            self.center.fold()
        if getattr(self, "_locator", None) is not None:
            return
        Toast.show(self.host, "Finding where you are…", kind="opening", busy=True)

        def found(latitude, longitude):
            self._locator = None
            self.set_place(self.cities.nearest(latitude, longitude))

        def failed(reason):
            self._locator = None
            Toast.show(self.host, reason, kind="warning", action=("Choose a city", self.open_location))

        self._locator = Locator(found, failed)
        self._locator.start()

    def _choose_city(self, place) -> None:
        if self.center.grown is not None:
            self.center.fold()
        self.set_place(place)

    # ── selection and details ─────────────────────────────────────────

    def select(self, selection) -> None:
        self.selection = selection
        self.view.select(selection)
        self.compass.queue_draw()
        if selection is None:
            self.details.show(subject=None)
        else:
            self._fill_details()
            # A computer opens the facts beside the sky; a phone keeps the sky and waits for Information.
            self.details.show(open=None if self.phone else True, subject=selection)
        self.show_bar()

    def toggle_details(self) -> None:
        self._fill_details()
        self.details.toggle()
        self.show_bar()

    def _details_closed(self) -> None:
        self.show_bar()

    def _fill_details(self) -> None:
        """The selection's facts, each with its icon, then its night: a curve of how high it climbs."""
        if self.selection is None or self.view.moment is None:
            return
        self.details.clear()
        kind, key = self.selection
        vector = self.view.vector_of(self.selection)
        name = self.name_of(self.selection)
        facts = []
        if vector is not None:
            facts.append(("compass", "Where now" if self.offset == timedelta(0) else "Where then",
                          self.where_words(vector)))
        if kind == "body":
            body = next(b for b in (self.view.moment.sun, self.view.moment.moon, *self.view.moment.planets)
                        if b.key == key)
            subtitle = {"sun": "Our star", "moon": sky.moon_phase_name(body.phase_angle)}.get(key, "Planet")
            if key == "moon":
                facts.append(("moon", "Lit", f"{round(body.phase_fraction * 100)}%"))
            elif key in ("mercury", "venus", "mars"):
                facts.append(("moon", "Phase", f"{round(body.phase_fraction * 100)}% lit"))
            facts.append(("sparkle", "Brightness", _magnitude_words(body.magnitude)))
            facts.append(("globe", "Distance", self._distance_words(key, body.distance_au)))
            rise_set = self._rise_set(self._ae_body(key))
            target = key
        elif kind == "star":
            star = self.catalog.stars[key]
            label = self.catalog.names.get(key, {})
            subtitle = f"Star in {self._constellation(label)}"
            if label.get("d") and label.get("n"):
                facts.append(("tag", "Also known as", f"{label['d']} {label.get('c', '')}".strip()))
            facts.append(("sparkle", "Brightness", _magnitude_words(star[2])))
            facts.append(("palette", "Colour", _colour_words(star[3])))
            ae.DefineStar(ae.Body.Star1, star[0] / 15, star[1], 1000)
            rise_set = self._rise_set(ae.Body.Star1)
            target = (star[0], star[1])
        else:
            entry = self.catalog.constellations[key]
            subtitle = "Constellation"
            ae.DefineStar(ae.Body.Star1, entry["ra"] / 15, entry["dec"], 1000)
            rise_set = self._rise_set(ae.Body.Star1)
            target = (entry["ra"], entry["dec"])
        facts += rise_set
        self.details.add_hero(name, subtitle)
        self.details.add_list([FactRow(icon, label, value, copy=False) for icon, label, value in facts])
        if key != "sun":
            self._add_night(target)

    def _add_night(self, target) -> None:
        """Tonight: how high it climbs from sunset to sunrise, and when it is best."""
        track = sky.night_track(target, self.when(), self.place.latitude, self.place.longitude, self.zone)
        if not track:
            return
        best = max(track, key=lambda sample: sample[1])
        self.details.add_section("Tonight")
        if best[1] <= 0:
            self.details.add_list([FactRow("eye", "Tonight", "Below the horizon all night", copy=False)])
            return
        if Sparkline is not None:
            curve = Sparkline([max(0.0, altitude) for _when, altitude, _az in track], capacity=len(track),
                              max_value=90, height=44, label=f"How high {self.name_of(self.selection)} climbs tonight")
            curve.set_margin_start(16)
            curve.set_margin_end(16)
            curve.set_margin_bottom(6)
            self.details.add(curve)
            ends = Gtk.Box(margin_start=16, margin_end=16, margin_bottom=4)
            for text, align in ((track[0][0].astimezone(self.zone).strftime("%H:%M"), 0),
                                (track[-1][0].astimezone(self.zone).strftime("%H:%M"), 1)):
                end = Gtk.Label(label=text, xalign=align, hexpand=True)
                end.add_css_class("dim-label")
                end.add_css_class("caption")
                ends.append(end)
            self.details.add(ends)
        when = best[0].astimezone(self.zone).strftime("%H:%M")
        direction = sky.direction_name(best[2])
        self.details.add_list([FactRow("arrow-up", "Highest", f"{when}, {best[1]:.0f}° up in the {direction}",
                                       copy=False)])

    def _rise_set(self, body) -> list[tuple[str, str]]:
        observer = ae.Observer(self.place.latitude, self.place.longitude, 0)
        start = sky.to_time(self.when())
        try:
            rise = ae.SearchRiseSet(body, observer, ae.Direction.Rise, start, 1.1)
            set_ = ae.SearchRiseSet(body, observer, ae.Direction.Set, start, 1.1)
        except Exception:  # noqa: BLE001
            return []
        if rise is None and set_ is None:
            vector = self.view.vector_of(self.selection)
            up = vector is not None and vector[2] > 0
            return [("eye", "Rises and sets", "Never sets here" if up else "Never rises here")]
        events = [(sky.to_datetime(at), icon, words) for at, icon, words in
                  ((rise, "sunrise", "Rises"), (set_, "sunset", "Sets")) if at is not None]
        # In the order they come: something up now sets before it rises again.
        return [(icon, words, _when_words(at, self.now(), self.zone)) for at, icon, words in sorted(events)]

    @staticmethod
    def _ae_body(key: str):
        return {"sun": ae.Body.Sun, "moon": ae.Body.Moon, **{name.lower(): body for body, name in sky.PLANETS}}[key]

    @staticmethod
    def _distance_words(key: str, au: float) -> str:
        km = au * 149_597_870.7
        if key == "moon":
            return f"{km:,.0f} km".replace(",", " ")
        minutes = au * 8.317
        if minutes < 90:
            return f"{au:.2f} AU · light takes {minutes:.0f} min"
        return f"{au:.2f} AU · light takes {minutes / 60:.1f} h"

    def _constellation(self, label: dict) -> str:
        return self.catalog.constellation_name(label.get("c", "")) if label.get("c") else "the sky"

    def where_words(self, vector, short: bool = False) -> str:
        azimuth, altitude = sky.az_alt(vector)
        if altitude < 0:
            return "Below the horizon"
        if altitude > 80:
            return "Overhead"
        direction = sky.direction_name(azimuth, short=short)
        if short:
            return f"{direction}, {altitude:.0f}° up"
        return f"{direction[0].upper()}{direction[1:]}, {altitude:.0f}° up"

    def name_of(self, selection) -> str:
        kind, key = selection
        if kind == "star":
            return self.catalog.star_name(key)
        if kind == "constellation":
            return self.catalog.constellation_name(key)
        return {"sun": "Sun", "moon": "Moon"}.get(key, key.capitalize())

    @staticmethod
    def icon_of(key: str) -> str:
        return {"sun": "sun", "moon": "moon"}.get(key, "circle-dot")

    def _closing(self, *_args):
        self._remember_look()
        if self._live_source:
            GLib.source_remove(self._live_source)
            self._live_source = 0
        return False


def _magnitude_words(magnitude: float) -> str:
    """Brightness the way a person reads it, with the astronomer's number after it."""
    number = f"{magnitude:+.1f}".replace("-", "−")
    if magnitude < -3:
        words = "Dazzling"
    elif magnitude < 0.5:
        words = "Very bright"
    elif magnitude < 2.5:
        words = "Bright"
    elif magnitude < 4.5:
        words = "Easy to see"
    else:
        words = "Faint"
    return f"{words} · magnitude {number}"


def _colour_words(bv: float) -> str:
    for limit, words in ((-0.1, "Blue-white"), (0.25, "White"), (0.55, "Yellow-white"), (0.85, "Yellow"),
                         (1.3, "Orange"), (99, "Red-orange")):
        if bv <= limit:
            return words
    return "White"


class VesperApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_startup(self):
        Adw.Application.do_startup(self)
        try:
            from luma_appkit import install_appkit, install_lumaui
            install_appkit()
            install_lumaui()
        except ImportError:
            pass

    def do_activate(self):
        window = self.props.active_window
        if window is None:
            window = VesperWindow(self)
            if os.environ.get("APP_WIDTH") or os.environ.get("APP_ACTION") or os.environ.get("APP_SHOT"):
                from .shots import prepare
                prepare(window)
        window.present()


def main(argv=None):
    return VesperApplication().run(argv or [])
