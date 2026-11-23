#!/usr/bin/env python3
"""Draw Vesper's icon: the evening star over a dusk horizon, on Luma's plate.

Vesper is the evening star, the first light in the sky after sunset. The star
is the object: cream, lit from the upper left, with Luma's edge light, a soft
glow and a faint contact shadow. Under it the last of the dusk glows violet in
the dip between two dark hills. The plate, its highlight and its rim are Luma's
own, at Luma's size, so the icon sits in the family's grid.

Usage: python3 -I tools/make_icon.py data/io.github.elomkdn.Vesper.svg
"""
import sys

P = "vsp"
PLATE = ("#4b3cda", "#1b137c")       # violet, two shades, the lighter at the upper left
DARK = "#0e0a48"
STAR = (585, 408, 190, 206)          # centre, half-width, half-height: 412 tall
WAIST = 0.17                         # how full the star's centre is, for presence at small sizes
DIP = (607, 716)                     # where the hills meet, under the star
GLOW = "#c7a2ff"
RIM = "#b9a3ff"


def star_path(cx, cy, w, h):
    k = h * WAIST
    return (f"M{cx} {cy - h}Q{cx + k} {cy - k} {cx + w} {cy}Q{cx + k} {cy + k} {cx} {cy + h}"
            f"Q{cx - k} {cy + k} {cx - w} {cy}Q{cx - k} {cy - k} {cx} {cy - h}Z")


def main(path):
    cx, cy, w, h = STAR
    star = star_path(cx, cy, w, h)
    dx, dy = DIP
    back_edge = f"M82 598C300 602 470 672 {dx} {dy}"
    front_edge = f"M942 636C850 642 722 672 {dx} {dy}C480 762 300 822 82 862"
    back = f"{back_edge}L942 770V942H82Z"
    front = f"{front_edge}V942H942Z"
    mask = lambda name, ox, oy: (
        f'<mask id="{P}-{name}" maskUnits="userSpaceOnUse" x="0" y="0" width="1024" height="1024">'
        f'<path d="{star}" fill="#fff"/><path d="{star}" fill="#000" transform="translate({ox} {oy})"/></mask>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
<defs>
<linearGradient id="{P}-pl" x1="0.2" y1="0" x2="0.8" y2="1"><stop offset="0" stop-color="{PLATE[0]}"/><stop offset="1" stop-color="{PLATE[1]}"/></linearGradient>
<radialGradient id="{P}-plh" cx="0.26" cy="0.12" r="0.8"><stop offset="0" stop-color="#fff" stop-opacity="0.2"/><stop offset="0.55" stop-color="#fff" stop-opacity="0.05"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
<linearGradient id="{P}-rim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0.42"/><stop offset="0.1" stop-color="#fff" stop-opacity="0"/><stop offset="0.86" stop-color="{DARK}" stop-opacity="0"/><stop offset="1" stop-color="{DARK}" stop-opacity="0.35"/></linearGradient>
<clipPath id="{P}-clip"><rect x="82" y="82" width="860" height="860" rx="202"/></clipPath>
<filter id="{P}-amb" x="-50%" y="-50%" width="200%" height="200%" color-interpolation-filters="sRGB"><feGaussianBlur stdDeviation="56"/></filter>
<filter id="{P}-sh" x="-50%" y="-50%" width="200%" height="200%" color-interpolation-filters="sRGB"><feGaussianBlur stdDeviation="22"/></filter>
<filter id="{P}-hsoft" x="-50%" y="-50%" width="200%" height="200%" color-interpolation-filters="sRGB"><feGaussianBlur stdDeviation="2"/></filter>
<radialGradient id="{P}-dusk" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="{GLOW}" stop-opacity="0.85"/><stop offset="0.45" stop-color="{GLOW}" stop-opacity="0.3"/><stop offset="1" stop-color="{GLOW}" stop-opacity="0"/></radialGradient>
<linearGradient id="{P}-back" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2b2192"/><stop offset="1" stop-color="#1a1369"/></linearGradient>
<linearGradient id="{P}-front" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1e1676"/><stop offset="1" stop-color="#110c4f"/></linearGradient>
<radialGradient id="{P}-glow" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#fff2c9" stop-opacity="0.42"/><stop offset="0.5" stop-color="#fff2c9" stop-opacity="0.1"/><stop offset="1" stop-color="#fff2c9" stop-opacity="0"/></radialGradient>
<linearGradient id="{P}-obj" x1="0.15" y1="0.05" x2="0.85" y2="0.95"><stop offset="0" stop-color="#fffdf2"/><stop offset="1" stop-color="#fae6b2"/></linearGradient>
{mask("hl", 7, 8.4)}
{mask("lo", -7, -8.4)}
</defs>
<g id="plate">
<rect x="82" y="82" width="860" height="860" rx="202" fill="url(#{P}-pl)"/>
<rect x="82" y="82" width="860" height="860" rx="202" fill="url(#{P}-plh)"/>
<g clip-path="url(#{P}-clip)">
<ellipse cx="{dx}" cy="{dy - 10}" rx="400" ry="190" fill="url(#{P}-dusk)"/>
<path d="{back}" fill="url(#{P}-back)"/>
<path d="{back_edge}" fill="none" stroke="{RIM}" stroke-width="4" stroke-linecap="round" opacity="0.55"/>
<path d="{front}" fill="url(#{P}-front)"/>
<path d="M942 636C850 642 722 672 {dx} {dy}" fill="none" stroke="{RIM}" stroke-width="4" stroke-linecap="round" opacity="0.5"/>
<path d="M{dx} {dy}C480 762 300 822 82 862" fill="none" stroke="{RIM}" stroke-width="3" stroke-linecap="round" opacity="0.14"/>
</g>
</g>
<g id="ambient-shadow" clip-path="url(#{P}-clip)"><ellipse cx="560" cy="700" rx="300" ry="150" fill="{DARK}" opacity="0.22" filter="url(#{P}-amb)"/></g>
<g id="object-shadow" clip-path="url(#{P}-clip)"><g opacity="0.24" filter="url(#{P}-sh)"><path d="{star}" fill="{DARK}" transform="translate(12 26)"/></g></g>
<g id="object-main">
<circle cx="{cx}" cy="{cy}" r="{int(h * 1.45)}" fill="url(#{P}-glow)"/>
<path d="{star}" fill="url(#{P}-obj)"/>
<g filter="url(#{P}-hsoft)"><rect width="1024" height="1024" fill="#8a6a2c" opacity="0.22" mask="url(#{P}-lo)"/><rect width="1024" height="1024" fill="#fff" mask="url(#{P}-hl)"/></g>
</g>
<g id="plate-rim" clip-path="url(#{P}-clip)"><rect x="82" y="82" width="860" height="860" rx="202" fill="none" stroke="url(#{P}-rim)" stroke-width="8"/></g>
</svg>
'''
    with open(path, "w", encoding="utf-8") as out:
        out.write(svg)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "io.github.elomkdn.Vesper.svg")
