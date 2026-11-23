#!/usr/bin/env python3
"""Build data/cities.json from GeoNames (CC BY 4.0): cities over 15,000 people.

Usage: python3 -I tools/build_cities.py <geonames dir> data/cities.json
Each entry: [name, ascii name or "", region, country, latitude, longitude, population, time zone].
"""
import json
import sys
from pathlib import Path


def main():
    source, target = Path(sys.argv[1]), Path(sys.argv[2])
    countries = {}
    for line in (source / "countryInfo.txt").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            parts = line.split("\t")
            countries[parts[0]] = parts[4]
    regions = {}
    for line in (source / "admin1CodesASCII.txt").read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            regions[parts[0]] = parts[1]
    cities = []
    for line in (source / "cities15000.txt").read_text(encoding="utf-8").splitlines():
        p = line.split("\t")
        name, ascii_name = p[1], p[2]
        country = countries.get(p[8], p[8])
        region = regions.get(f"{p[8]}.{p[10]}", "")
        cities.append([name, ascii_name if ascii_name != name else "", region, country,
                       round(float(p[4]), 3), round(float(p[5]), 3), int(p[14] or 0), p[17]])
    cities.sort(key=lambda c: -c[6])
    target.write_text(json.dumps({"source": "GeoNames, CC BY 4.0", "cities": cities},
                                 separators=(",", ":"), ensure_ascii=False))
    print(f"{len(cities)} cities, {target.stat().st_size // 1024} KiB")


if __name__ == "__main__":
    main()
