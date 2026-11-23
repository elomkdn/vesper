#!/usr/bin/env python3
"""Build data/sky.json from the d3-celestial catalogue (BSD-3-Clause, Olaf Frohn).

Usage: python3 -I tools/build_catalog.py <d3-celestial data dir> data/sky.json

Keeps what Vesper draws: stars to magnitude 6 with their colour index, the
constellation figures and label points, proper names, and the Milky Way as a
grid of glow points sampled from its five outline levels. Coordinates are J2000
right ascension and declination in degrees.
"""
import json
import math
import sys
from pathlib import Path


def ra_of(lon):
    return lon + 360 if lon < 0 else lon


def r(value, digits=3):
    return round(value, digits)


def stars(source, names):
    out = []
    labels = {}
    for feature in source["features"]:
        lon, dec = feature["geometry"]["coordinates"]
        props = feature["properties"]
        try:
            bv = float(props.get("bv") or 0.6)
        except ValueError:
            bv = 0.6
        index = len(out)
        out.append([r(ra_of(lon)), r(dec), r(props["mag"], 2), r(bv, 2)])
        entry = names.get(str(feature["id"]))
        if entry:
            label = {}
            if entry.get("name"):
                label["n"] = entry["name"]
            designation = entry.get("bayer") or entry.get("flam") or ""
            if designation:
                label["d"] = designation
            if entry.get("c"):
                label["c"] = entry["c"]
            if label:
                labels[index] = label
    return out, labels


def faint(source):
    """Stars from magnitude 6 to 7.2, shown only when zoomed in."""
    out = []
    for feature in source["features"]:
        mag = feature["properties"]["mag"]
        if 6.0 < mag <= 7.2:
            lon, dec = feature["geometry"]["coordinates"]
            try:
                bv = float(feature["properties"].get("bv") or 0.6)
            except ValueError:
                bv = 0.6
            out.append([r(ra_of(lon)), r(dec), r(mag, 2), r(bv, 2)])
    return out


def lines(source):
    figures = {}
    for feature in source["features"]:
        figures[feature["id"]] = [[[r(ra_of(lon), 2), r(dec, 2)] for lon, dec in line]
                                  for line in feature["geometry"]["coordinates"]]
    return figures


def constellations(source):
    out = {}
    for feature in source["features"]:
        lon, dec = feature["geometry"]["coordinates"]
        props = feature["properties"]
        out[feature["id"]] = {"name": props["name"], "ra": r(ra_of(lon), 2),
                              "dec": r(dec, 2), "rank": int(props.get("rank") or 3)}
    return out


def _inside(lon, lat, ring):
    """Even-odd test with the ring unwrapped around the point (rings never circle a pole)."""
    inside = False
    count = len(ring)
    for i in range(count):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % count]
        x1 = lon + ((x1 - lon + 180) % 360 - 180)
        x2 = x1 + ((x2 - x1 + 180) % 360 - 180)
        if (y1 > lat) != (y2 > lat):
            x = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if x > lon:
                inside = not inside
    return inside


def milky_way(source, step=1.5):
    levels = []
    for feature in sorted(source["features"], key=lambda f: f["id"]):
        rings = [ring for polygon in feature["geometry"]["coordinates"] for ring in polygon]
        boxes = []
        for ring in rings:
            lats = [p[1] for p in ring]
            boxes.append((min(lats), max(lats)))
        levels.append(list(zip(rings, boxes)))
    points = []
    dec = -90 + step / 2
    while dec < 90:
        ring_step = step / max(math.cos(math.radians(dec)), 0.05)
        count = max(1, int(round(360 / ring_step)))
        for k in range(count):
            ra = (k + 0.5) * 360 / count
            lon = ra if ra <= 180 else ra - 360
            weight = 0
            for level, rings in enumerate(levels, start=1):
                hits = sum(1 for ring, (low, high) in rings if low <= dec <= high and _inside(lon, dec, ring))
                if hits % 2:
                    weight = level
            if weight:
                points.append([r(ra, 2), r(dec, 2), weight])
        dec += step
    return points


def main():
    source, target = Path(sys.argv[1]), Path(sys.argv[2])
    load = lambda name: json.loads((source / name).read_text())
    star_list, labels = stars(load("stars.6.json"), load("starnames.json"))
    sky = {
        "source": "d3-celestial by Olaf Frohn, BSD-3-Clause",
        "stars": star_list,
        "names": labels,
        "lines": lines(load("constellations.lines.json")),
        "constellations": constellations(load("constellations.json")),
        "milky_way": milky_way(load("mw.json")),
        "faint": faint(load("stars.8.json")),
    }
    target.write_text(json.dumps(sky, separators=(",", ":"), ensure_ascii=False))
    print(f"{len(star_list)} stars, {len(labels)} names, {len(sky['lines'])} figures, "
          f"{len(sky['milky_way'])} Milky Way points, {target.stat().st_size // 1024} KiB")


if __name__ == "__main__":
    main()
