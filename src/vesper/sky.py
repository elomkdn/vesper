# SPDX-License-Identifier: GPL-3.0-or-later
"""The sky at a moment and a place: where everything is, and what tonight holds.

No GTK here, so the whole model is testable without a display. Positions are
horizontal unit vectors in astronomy-engine's frame: x north, y west, z up.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import astronomy as ae

PLANETS = (
    (ae.Body.Mercury, "Mercury"), (ae.Body.Venus, "Venus"), (ae.Body.Mars, "Mars"),
    (ae.Body.Jupiter, "Jupiter"), (ae.Body.Saturn, "Saturn"), (ae.Body.Uranus, "Uranus"),
    (ae.Body.Neptune, "Neptune"),
)
NAKED_EYE = {"Mercury", "Venus", "Mars", "Jupiter", "Saturn"}
DIRECTIONS = ("north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west")
SHORT_DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def unit(ra_deg: float, dec_deg: float) -> tuple[float, float, float]:
    ra, dec = math.radians(ra_deg), math.radians(dec_deg)
    c = math.cos(dec)
    return (c * math.cos(ra), c * math.sin(ra), math.sin(dec))


def horizontal(azimuth: float, altitude: float) -> tuple[float, float, float]:
    az, alt = math.radians(azimuth), math.radians(altitude)
    c = math.cos(alt)
    return (c * math.cos(az), -c * math.sin(az), math.sin(alt))


def az_alt(vector) -> tuple[float, float]:
    x, y, z = vector
    return (math.degrees(math.atan2(-y, x)) % 360, math.degrees(math.asin(max(-1.0, min(1.0, z)))))


def direction_name(azimuth: float, short: bool = False) -> str:
    names = SHORT_DIRECTIONS if short else DIRECTIONS
    return names[int(((azimuth % 360) + 22.5) // 45) % 8]


def to_time(moment: datetime) -> ae.Time:
    moment = moment.astimezone(timezone.utc)
    return ae.Time.Make(moment.year, moment.month, moment.day, moment.hour, moment.minute,
                        moment.second + moment.microsecond / 1e6)


def to_datetime(time: ae.Time) -> datetime:
    return time.Utc().replace(tzinfo=timezone.utc)


@dataclass
class Catalog:
    stars: list            # [ra, dec, mag, bv]
    vectors: list          # unit vectors, J2000 equator
    names: dict            # star index -> {"n": proper name, "d": designation, "c": constellation}
    lines: dict            # constellation id -> polylines of [ra, dec]
    line_vectors: dict     # constellation id -> polylines of unit vectors
    constellations: dict   # id -> {"name", "ra", "dec", "rank"}
    milky_way: list        # [ra, dec, level]
    milky_vectors: list
    faint: list = field(default_factory=list)          # [ra, dec, mag, bv], magnitude 6 to 7.2
    faint_vectors: list = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "Catalog":
        data = json.loads(Path(path).read_text())
        stars = data["stars"]
        lines = data["lines"]
        milky = data["milky_way"]
        return cls(stars=stars, vectors=[unit(s[0], s[1]) for s in stars],
                   names={int(k): v for k, v in data["names"].items()}, lines=lines,
                   line_vectors={k: [[unit(*p) for p in line] for line in figure] for k, figure in lines.items()},
                   constellations=data["constellations"], milky_way=milky,
                   milky_vectors=[unit(p[0], p[1]) for p in milky],
                   faint=data.get("faint", []), faint_vectors=[unit(s[0], s[1]) for s in data.get("faint", [])])

    def star_name(self, index: int) -> str:
        entry = self.names.get(index, {})
        if entry.get("n"):
            return entry["n"]
        if entry.get("d") and entry.get("c"):
            return f"{entry['d']} {entry['c']}"
        return f"HIP star {index}"

    def constellation_name(self, key: str) -> str:
        return self.constellations.get(key, {}).get("name", key)


@dataclass
class Body:
    """Something that moves across the sky: the Sun, the Moon, a planet."""
    key: str
    name: str
    vector: tuple
    magnitude: float
    distance_au: float
    phase_fraction: float = 1.0   # lit part of the disc, 0..1
    phase_angle: float = 0.0      # Moon: 0 new, 90 first quarter, 180 full, 270 last quarter

    @property
    def azimuth(self) -> float:
        return az_alt(self.vector)[0]

    @property
    def altitude(self) -> float:
        return az_alt(self.vector)[1]


@dataclass
class Moment:
    """Everything that depends on the time and place."""
    when: datetime
    latitude: float
    longitude: float
    matrix: tuple                       # rows of the J2000-equator -> horizontal rotation
    sun: Body
    moon: Body
    planets: list = field(default_factory=list)

    def to_horizontal(self, v):
        m = self.matrix
        return (m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
                m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
                m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2])

    @property
    def light(self) -> str:
        """day, dusk (sun just below the horizon) or night, for the sky's colour."""
        altitude = self.sun.altitude
        if altitude > -0.8:
            return "day"
        if altitude > -12:
            return "dusk"
        return "night"


def _body(observer: ae.Observer, time: ae.Time, body: ae.Body, key: str, name: str) -> Body:
    equator = ae.Equator(body, time, observer, True, True)
    hor = ae.Horizon(time, observer, equator.ra, equator.dec, ae.Refraction.Airless)
    vector = horizontal(hor.azimuth, hor.altitude)
    try:
        light = ae.Illumination(body, time)
        magnitude, fraction = light.mag, light.phase_fraction
    except Exception:  # noqa: BLE001 - the Sun has no phase in some versions
        magnitude, fraction = (-26.7 if body == ae.Body.Sun else 0.0), 1.0
    return Body(key, name, vector, magnitude, equator.dist, fraction)


def moment(when: datetime, latitude: float, longitude: float) -> Moment:
    time = to_time(when)
    observer = ae.Observer(latitude, longitude, 0)
    rotation = ae.Rotation_EQJ_HOR(time, observer).rot
    # astronomy-engine stores column-major: rot[i][j] maps component i to j.
    matrix = tuple(tuple(rotation[j][i] for j in range(3)) for i in range(3))
    sun = _body(observer, time, ae.Body.Sun, "sun", "Sun")
    moon = _body(observer, time, ae.Body.Moon, "moon", "Moon")
    moon.phase_angle = ae.MoonPhase(time)
    planets = [_body(observer, time, body, name.lower(), name) for body, name in PLANETS]
    return Moment(when, latitude, longitude, matrix, sun, moon, planets)


def moon_phase_name(angle: float) -> str:
    names = ("New moon", "Waxing crescent", "First quarter", "Waxing gibbous",
             "Full moon", "Waning gibbous", "Last quarter", "Waning crescent")
    return names[int(((angle % 360) + 22.5) // 45) % 8]


@dataclass
class Highlight:
    key: str          # body key, or "dark"
    title: str
    detail: str       # where, how
    icon: str
    best: datetime | None = None
    time: str = ""    # the moment, shown at the row's end


def _search(body, observer, direction, start, days=1.2, altitude=None):
    try:
        if altitude is None:
            found = ae.SearchRiseSet(body, observer, direction, start, days)
        else:
            found = ae.SearchAltitude(body, observer, direction, start, days, altitude)
    except Exception:  # noqa: BLE001 - polar days and nights have no event
        return None
    return to_datetime(found) if found else None


def night_window(when: datetime, latitude: float, longitude: float, zone=None) -> tuple[datetime, datetime]:
    """The coming (or current) night: sunset to sunrise, around `when`."""
    observer = ae.Observer(latitude, longitude, 0)
    noon = when.astimezone(zone).replace(hour=12, minute=0, second=0, microsecond=0)
    if when.astimezone(zone).hour < 6:
        noon -= timedelta(days=1)
    start = to_time(noon)
    sunset = _search(ae.Body.Sun, observer, ae.Direction.Set, start) or noon + timedelta(hours=7)
    sunrise = _search(ae.Body.Sun, observer, ae.Direction.Rise, to_time(sunset)) or sunset + timedelta(hours=11)
    return sunset, sunrise


def next_dark(when: datetime, latitude: float, longitude: float) -> datetime:
    """The next moment the sky is properly dark: night, or deep twilight where nights stay light."""
    observer = ae.Observer(latitude, longitude, 0)
    start = to_time(when)
    for altitude in (-18, -12, -6):
        found = _search(ae.Body.Sun, observer, ae.Direction.Set, start, 1.2, altitude)
        if found:
            return found
    return when + timedelta(hours=12)


def tonight(when: datetime, latitude: float, longitude: float, zone=None) -> list[Highlight]:
    """What is worth looking at tonight, best first. Times read in `zone` (None: the device's)."""
    def clock(moment_at):
        return moment_at.astimezone(zone).strftime("%H:%M")
    observer = ae.Observer(latitude, longitude, 0)
    sunset, sunrise = night_window(when, latitude, longitude, zone)
    found = []
    dark = _search(ae.Body.Sun, observer, ae.Direction.Set, to_time(sunset), 1, -18)
    if dark and dark < sunrise:
        found.append(Highlight("dark", "Fully dark", f"Sunset {clock(sunset)} · sunrise {clock(sunrise)}",
                               "sunset", dark, clock(dark)))
    else:
        found.append(Highlight("dark", "Sunset", f"Never fully dark tonight · sunrise {clock(sunrise)}",
                               "sunset", sunset, clock(sunset)))

    samples = []
    step = timedelta(minutes=15)
    moment_at = sunset
    while moment_at <= sunrise:
        samples.append(moment_at)
        moment_at += step

    phase = ae.MoonPhase(to_time(when))
    lit = ae.Illumination(ae.Body.Moon, to_time(when)).phase_fraction
    moon_best = _best(observer, ae.Body.Moon, samples, minimum=5)
    rise = _search(ae.Body.Moon, observer, ae.Direction.Rise, to_time(sunset - timedelta(hours=6)), 1.2)
    if moon_best:
        best, azimuth, altitude = moon_best
        detail = f"{round(lit * 100)}% lit · highest in the {direction_name(azimuth)}"
        found.append(Highlight("moon", moon_phase_name(phase), detail, "moon", best, clock(best)))
    else:
        found.append(Highlight("moon", moon_phase_name(phase), f"{round(lit * 100)}% lit · down all night",
                               "moon", None, ""))

    for body, name in PLANETS:
        if name not in NAKED_EYE:
            continue
        result = _best(observer, body, samples, minimum=8)
        if result is None:
            continue
        best, azimuth, altitude = result
        height = "High" if altitude > 45 else "Low" if altitude < 20 else "Halfway up"
        found.append(Highlight(name.lower(), name, f"{height} in the {direction_name(azimuth)}", "circle-dot",
                               best, clock(best)))
    _ = rise
    # Darkness first, then everything in the order the night brings it.
    dark_row, rest = found[0], found[1:]
    rest.sort(key=lambda h: (h.best is None, h.best or sunrise))
    return [dark_row, *rest]


def _best(observer, body, samples, minimum):
    best = None
    for moment_at in samples:
        time = to_time(moment_at)
        sun = ae.Horizon(time, observer, *_radec(ae.Body.Sun, time, observer), ae.Refraction.Normal)
        if sun.altitude > -8:
            continue
        hor = ae.Horizon(time, observer, *_radec(body, time, observer), ae.Refraction.Normal)
        if hor.altitude >= minimum and (best is None or hor.altitude > best[2]):
            best = (moment_at, hor.azimuth, hor.altitude)
    return best


def _radec(body, time, observer):
    equator = ae.Equator(body, time, observer, True, True)
    return equator.ra, equator.dec


def clock(moment_at: datetime, zone=None) -> str:
    return moment_at.astimezone(zone).strftime("%H:%M")


def day_start(when: datetime, zone=None) -> datetime:
    """The local noon that opens the day-and-night holding `when` (noon to noon), in UTC."""
    local = when.astimezone(zone)
    noon = local.replace(hour=12, minute=0, second=0, microsecond=0)
    if local.hour < 12:
        noon = (noon - timedelta(days=1)).replace(hour=12)
    return noon.astimezone(timezone.utc)


def night_track(target, when: datetime, latitude: float, longitude: float, zone=None, step_minutes: int = 15):
    """Altitude through the night around `when`, sunset to sunrise: [(moment, altitude, azimuth)].

    `target` is a body key ("moon", "jupiter"…) or a (ra, dec) pair in degrees.
    """
    observer = ae.Observer(latitude, longitude, 0)
    sunset, sunrise = night_window(when, latitude, longitude, zone)
    if isinstance(target, str):
        body = {"sun": ae.Body.Sun, "moon": ae.Body.Moon,
                **{name.lower(): b for b, name in PLANETS}}[target]
    else:
        ae.DefineStar(ae.Body.Star2, target[0] / 15, target[1], 1000)
        body = ae.Body.Star2
    track = []
    moment_at = sunset
    while moment_at <= sunrise:
        time = to_time(moment_at)
        hor = ae.Horizon(time, observer, *_radec(body, time, observer), ae.Refraction.Normal)
        track.append((moment_at, hor.altitude, hor.azimuth))
        moment_at += timedelta(minutes=step_minutes)
    return track
