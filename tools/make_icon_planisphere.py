#!/usr/bin/env python3
"""Draw Vesper's icon in Luma's family style: a planisphere on an indigo plate.

A planisphere is the paper star wheel stargazers turn to see what is up
tonight, which is what Vesper does. A white disc with an hour scale round its
edge, and a window onto a night sky: a few stars, one figure, and the evening
star, brightest of all.

Usage: python3 -I tools/make_icon_planisphere.py out.svg   (the earlier planisphere design, kept for reference)
"""
import math
import sys

P = "vsp"
PLATE = ("#5a6cff", "#2732c2")
DARK = "#141a6e"
CX, CY, R = 512, 488, 228            # the disc: 456 across, inside the guide's 400 to 460
WX, WY, WRX, WRY = 512, 466, 182, 164  # the window onto the sky, a little high on the disc


def main(path):
    disc = f'<circle cx="{CX}" cy="{CY}" r="{R}"'
    mask = lambda name, dx, dy: (
        f'<mask id="{P}-{name}" maskUnits="userSpaceOnUse" x="0" y="0" width="1024" height="1024">'
        f'{disc} fill="#fff"/>{disc} fill="#000" transform="translate({dx} {dy})"/></mask>')
    # The hour scale round the rim: 24 ticks, every sixth longer.
    ticks = []
    for i in range(24):
        a = math.radians(i * 15 - 90)
        inner = R - (34 if i % 6 == 0 else 24)
        outer = R - 12
        ticks.append(f'<line x1="{CX + inner * math.cos(a):.1f}" y1="{CY + inner * math.sin(a):.1f}" '
                     f'x2="{CX + outer * math.cos(a):.1f}" y2="{CY + outer * math.sin(a):.1f}" '
                     f'stroke="{DARK}" stroke-width="{9 if i % 6 == 0 else 6}" stroke-linecap="round" '
                     f'opacity="{0.34 if i % 6 == 0 else 0.2}"/>')
    # A figure (a little W, like Cassiopeia) and loose stars, then the evening star.
    figure = [(424, 414), (466, 462), (510, 426), (556, 472), (602, 422)]
    loose = [(600, 540, 8), (392, 480, 6), (560, 372, 6), (642, 470, 6), (470, 354, 5), (520, 566, 6)]
    figure_svg = (f'<polyline points="{" ".join(f"{x},{y}" for x, y in figure)}" fill="none" stroke="#fff" '
                  f'stroke-width="6" stroke-linecap="round" stroke-linejoin="round" opacity="0.42"/>'
                  + "".join(f'<circle cx="{x}" cy="{y}" r="11" fill="#fff"/>' for x, y in figure)
                  + "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#fff" opacity="0.75"/>' for x, y, r in loose))
    vesper = (f'<circle cx="452" cy="532" r="58" fill="url(#{P}-glow)"/>'
              f'<path d="M452 492 Q457 527 492 532 Q457 537 452 572 Q447 537 412 532 Q447 527 452 492Z" fill="#fff"/>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
<defs>
<linearGradient id="{P}-pl" x1="0.2" y1="0" x2="0.8" y2="1"><stop offset="0" stop-color="{PLATE[0]}"/><stop offset="1" stop-color="{PLATE[1]}"/></linearGradient>
<radialGradient id="{P}-plh" cx="0.26" cy="0.12" r="0.8"><stop offset="0" stop-color="#fff" stop-opacity="0.2"/><stop offset="0.55" stop-color="#fff" stop-opacity="0.05"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
<linearGradient id="{P}-rim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0.42"/><stop offset="0.1" stop-color="#fff" stop-opacity="0"/><stop offset="0.86" stop-color="{DARK}" stop-opacity="0"/><stop offset="1" stop-color="{DARK}" stop-opacity="0.35"/></linearGradient>
<clipPath id="{P}-clip"><rect x="82" y="82" width="860" height="860" rx="202"/></clipPath>
<filter id="{P}-amb" x="-50%" y="-50%" width="200%" height="200%" color-interpolation-filters="sRGB"><feGaussianBlur stdDeviation="56"/></filter>
<filter id="{P}-sh" x="-50%" y="-50%" width="200%" height="200%" color-interpolation-filters="sRGB"><feGaussianBlur stdDeviation="22"/></filter>
<filter id="{P}-hsoft" x="-50%" y="-50%" width="200%" height="200%" color-interpolation-filters="sRGB"><feGaussianBlur stdDeviation="2"/></filter>
<filter id="{P}-inset" x="-50%" y="-50%" width="200%" height="200%" color-interpolation-filters="sRGB"><feGaussianBlur stdDeviation="10"/></filter>
<linearGradient id="{P}-obj" x1="0.1" y1="0.05" x2="0.9" y2="0.95"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#dfe7f2"/></linearGradient>
<linearGradient id="{P}-sky" x1="0.2" y1="0" x2="0.8" y2="1"><stop offset="0" stop-color="#262f8f"/><stop offset="1" stop-color="#0e1352"/></linearGradient>
<radialGradient id="{P}-glow" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#fff6dc" stop-opacity="0.7"/><stop offset="1" stop-color="#fff6dc" stop-opacity="0"/></radialGradient>
<clipPath id="{P}-win"><ellipse cx="{WX}" cy="{WY}" rx="{WRX}" ry="{WRY}"/></clipPath>
{mask("hl", 7, 8.4)}
{mask("lo", -7, -8.4)}
</defs>
<g id="plate"><rect x="82" y="82" width="860" height="860" rx="202" fill="url(#{P}-pl)"/><rect x="82" y="82" width="860" height="860" rx="202" fill="url(#{P}-plh)"/></g>
<g id="ambient-shadow" clip-path="url(#{P}-clip)"><ellipse cx="520" cy="700" rx="320" ry="170" fill="{DARK}" opacity="0.38" filter="url(#{P}-amb)"/></g>
<g id="object-shadow" clip-path="url(#{P}-clip)"><g opacity="0.32" filter="url(#{P}-sh)"><circle cx="{CX + 12}" cy="{CY + 26}" r="{R}" fill="{DARK}"/></g></g>
<g id="object-main">
{disc} fill="url(#{P}-obj)"/>
{"".join(ticks)}
<ellipse cx="{WX}" cy="{WY}" rx="{WRX}" ry="{WRY}" fill="url(#{P}-sky)"/>
<g clip-path="url(#{P}-win)">
<ellipse cx="{WX}" cy="{WY - 14}" rx="{WRX + 6}" ry="{WRY + 4}" fill="none" stroke="#000" stroke-width="22" opacity="0.35" filter="url(#{P}-inset)"/>
{figure_svg}
{vesper}
</g>
<g filter="url(#{P}-hsoft)"><rect width="1024" height="1024" fill="#5a628c" opacity="0.25" mask="url(#{P}-lo)"/><rect width="1024" height="1024" fill="#fff" mask="url(#{P}-hl)"/></g>
</g>
<g id="plate-rim" clip-path="url(#{P}-clip)"><rect x="82" y="82" width="860" height="860" rx="202" fill="none" stroke="url(#{P}-rim)" stroke-width="8"/></g>
</svg>
'''
    with open(path, "w", encoding="utf-8") as out:
        out.write(svg)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "io.github.elomkdn.Vesper.svg")
