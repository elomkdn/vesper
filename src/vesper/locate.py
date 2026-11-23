# SPDX-License-Identifier: GPL-3.0-or-later
"""Where you are, asked once of the desktop's Location portal, at city accuracy.

Nothing is sent anywhere by Vesper: the portal asks you, the system works out
the position, and Vesper only turns it into the nearest bundled city (for its
name and time zone).
"""
from __future__ import annotations

import secrets

from gi.repository import Gio, GLib

DESKTOP = "org.freedesktop.portal.Desktop"
PATH = "/org/freedesktop/portal/desktop"
CITY = 2            # the portal's accuracy levels: 0 none … 2 city … 5 exact
PATIENCE = 20       # seconds before giving up


class Locator:
    """`Locator(on_found, on_failed).start()`: on_found(latitude, longitude) or on_failed(reason), once."""

    def __init__(self, on_found, on_failed):
        self.on_found, self.on_failed = on_found, on_failed
        self.bus = None
        self.session = None
        self._subscriptions = []
        self._timeout = 0
        self._done = False

    def start(self) -> None:
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error:
            self._finish(failed="No location service")
            return
        sender = self.bus.get_unique_name()[1:].replace(".", "_")
        token, request = f"vesper{secrets.token_hex(4)}", f"vesper{secrets.token_hex(4)}"
        self.session = f"{PATH}/session/{sender}/{token}"
        self._listen("org.freedesktop.portal.Location", "LocationUpdated", None, self._updated)
        self._listen("org.freedesktop.portal.Request", "Response", f"{PATH}/request/{sender}/{request}",
                     self._answered)
        self._timeout = GLib.timeout_add_seconds(PATIENCE, self._gave_up)
        options = {"session_handle_token": GLib.Variant("s", token), "accuracy": GLib.Variant("u", CITY)}
        self._call("CreateSession", GLib.Variant("(a{sv})", (options,)),
                   lambda: self._call("Start", GLib.Variant("(osa{sv})", (self.session, "", {
                       "handle_token": GLib.Variant("s", request)})), None))

    def cancel(self) -> None:
        self._finish()

    # ── portal ────────────────────────────────────────────────────────

    def _listen(self, interface, signal, path, callback):
        self._subscriptions.append(self.bus.signal_subscribe(
            DESKTOP, interface, signal, path, None, Gio.DBusSignalFlags.NONE,
            lambda _bus, _sender, _path, _interface, _signal, values: callback(values)))

    def _call(self, method, arguments, then):
        def done(bus, result):
            try:
                bus.call_finish(result)
            except GLib.Error as error:
                self._finish(failed=_reason(error.message))
                return
            if then is not None:
                then()
        self.bus.call(DESKTOP, PATH, "org.freedesktop.portal.Location", method, arguments, None,
                      Gio.DBusCallFlags.NONE, -1, None, done)

    def _answered(self, values):
        response, _results = values.unpack()
        if response != 0:
            self._finish(failed="Location wasn't allowed" if response == 1 else "Couldn't get your location")

    def _updated(self, values):
        session, where = values.unpack()
        if session != self.session:
            return
        try:
            latitude, longitude = float(where["Latitude"]), float(where["Longitude"])
        except (KeyError, TypeError, ValueError):
            self._finish(failed="Couldn't get your location")
            return
        self._finish(found=(latitude, longitude))

    def _gave_up(self):
        self._timeout = 0
        self._finish(failed="Couldn't find where you are")
        return GLib.SOURCE_REMOVE

    def _finish(self, *, found=None, failed=None):
        if self._done:
            return
        self._done = True
        if self._timeout:
            GLib.source_remove(self._timeout)
            self._timeout = 0
        if self.bus is not None:
            for subscription in self._subscriptions:
                self.bus.signal_unsubscribe(subscription)
            self._subscriptions = []
            if self.session:
                self.bus.call(DESKTOP, self.session, "org.freedesktop.portal.Session", "Close", None, None,
                              Gio.DBusCallFlags.NONE, -1, None, lambda bus, result: _quietly(bus, result))
        if found is not None:
            self.on_found(*found)
        elif failed is not None:
            self.on_failed(failed)


def _reason(message: str) -> str:
    """What went wrong, in words a person can act on."""
    if "disabled" in message.lower():
        return "Location is turned off in Settings"
    if "NotAllowed" in message:
        return "Location wasn't allowed"
    if "UnknownMethod" in message or "ServiceUnknown" in message or "UnknownInterface" in message:
        return "Location isn't available here"
    return "Couldn't get your location"


def _quietly(bus, result):
    try:
        bus.call_finish(result)
    except GLib.Error:
        pass
