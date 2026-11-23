# SPDX-License-Identifier: GPL-3.0-or-later
"""Where the sky is seen from: a city from the bundled list, or coordinates typed in.

Everything is on the device; looking up a city never leaves it.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


@dataclass(frozen=True)
class Place:
    name: str
    region: str
    latitude: float
    longitude: float
    zone: str = ""          # IANA time zone; empty means the device's own

    def saved(self) -> dict:
        return {"name": self.name, "region": self.region, "lat": self.latitude, "lon": self.longitude,
                "zone": self.zone}

    @property
    def tzinfo(self):
        if self.zone:
            try:
                from zoneinfo import ZoneInfo
                return ZoneInfo(self.zone)
            except Exception:  # noqa: BLE001 - an unknown zone falls back to the device's
                return None
        return None

    @classmethod
    def from_saved(cls, value) -> "Place | None":
        if not isinstance(value, dict):
            return None
        try:
            return cls(str(value["name"]), str(value.get("region", "")), float(value["lat"]), float(value["lon"]),
                       str(value.get("zone", "")))
        except (KeyError, TypeError, ValueError):
            return None


_COORDINATES = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?)\s*°?\s*([NSns])?\s*[,; ]\s*(-?\d+(?:[.,]\d+)?)\s*°?\s*([EWew])?\s*$")


def parse_coordinates(text: str) -> Place | None:
    match = _COORDINATES.match(text)
    if not match:
        return None
    lat = float(match.group(1).replace(",", "."))
    lon = float(match.group(3).replace(",", "."))
    if (match.group(2) or "").upper() == "S":
        lat = -abs(lat)
    if (match.group(4) or "").upper() == "W":
        lon = -abs(lon)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return Place(f"{abs(lat):.2f}° {ns}, {abs(lon):.2f}° {ew}", "Coordinates", lat, lon)


class Cities:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._rows = None

    def _load(self):
        if self._rows is None:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))["cities"]
            except (OSError, ValueError, KeyError):
                data = []
            self._rows = [(_fold(row[0]), _fold(row[1]) if row[1] else "", row) for row in data]
        return self._rows

    def search(self, text: str, limit: int = 8) -> list[Place]:
        query = _fold(text.strip())
        if not query:
            return []
        typed = parse_coordinates(text)
        found = [typed] if typed else []
        city, _, region_hint = query.partition(",")
        city, region_hint = city.strip(), region_hint.strip()
        starts, contains = [], []
        for folded, ascii_name, row in self._load():
            if folded.startswith(city) or (ascii_name and ascii_name.startswith(city)):
                bucket = starts
            elif len(city) >= 3 and city in folded:
                bucket = contains
            else:
                continue
            if region_hint and region_hint not in _fold(f"{row[2]} {row[3]}"):
                continue
            bucket.append(row)
            if len(starts) >= limit:
                break
        for row in (starts + contains)[:limit - len(found)]:
            region = ", ".join(part for part in (row[2], row[3]) if part and part != row[0])
            found.append(Place(row[0], region, row[4], row[5], row[7] if len(row) > 7 else ""))
        return found

    def nearest(self, latitude: float, longitude: float) -> Place:
        """The bundled city closest to a position, keeping the position itself.

        Its name and time zone stand for where you are; far from any town, the
        coordinates name the place and the closest city still gives the time zone.
        """
        cos_lat = math.cos(math.radians(latitude))
        found = []
        for _folded, _ascii, row in self._load():
            dlat = row[4] - latitude
            dlon = (row[5] - longitude + 180) % 360 - 180
            found.append((math.hypot(dlat, dlon * cos_lat) * 111, row))
        typed = parse_coordinates(f"{latitude:.4f}, {longitude:.4f}")
        if not found:
            return typed
        closest = min(distance for distance, _row in found)
        # A city's districts are listed too: within a short drive, the biggest town names it.
        near = [(row[6] if len(row) > 6 else 0, -distance, row) for distance, row in found
                if distance <= max(15.0, closest + 5)]
        best = max(near)[2]
        zone = best[7] if len(best) > 7 else ""
        if closest > 60:
            return Place(typed.name, f"Near {best[0]}", latitude, longitude, zone)
        region = ", ".join(part for part in (best[2], best[3]) if part and part != best[0])
        return Place(best[0], region, latitude, longitude, zone)
