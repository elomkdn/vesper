#!/usr/bin/env python3
"""Vesper's icon, sky map version, in Luma's family style: a printed star chart on an indigo plate.

A white card turned a few degrees, like Notes' note, with a round chart of the
night on it: the Big Dipper with its lines, a few loose stars, a faint grid,
the four points of the compass ticked round its edge, and two lines of print.

Usage: python3 -I tools/make_icon_skymap.py out.svg
"""
import sys

P = "vsp"
PLATE = ("#5a6cff", "#2732c2")
DARK = "#141a6e"
CARD = (296, 252, 432, 460, 38)       # x, y, width, height, radius: 432 across
CX, CY, R = 512, 446, 168             # the chart
TILT = -4
DIPPER = [(88, 30), (90, 52), (68, 58), (64, 38), (46, 34), (30, 32), (12, 42)]
LINES = [(0, 1), (1, 2), (2, 3), (3, 0), (3, 4), (4, 5), (5, 6)]
LOOSE = [(424, 352, 4), (590, 330, 5), (606, 552, 4), (430, 540, 5), (520, 586, 3.5), (378, 452, 3.5),
         (640, 450, 3.5)]


def main(path):
    x, y, w, h, r = CARD
    card = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}"'
    turn = f'transform="rotate({TILT} 512 482)"'
    stars = [(CX + (u - 50) * 2.75, CY + (v - 44) * 2.75) for u, v in DIPPER]
    lines = "".join(f'<line x1="{stars[a][0]:.1f}" y1="{stars[a][1]:.1f}" x2="{stars[b][0]:.1f}" '
                    f'y2="{stars[b][1]:.1f}"/>' for a, b in LINES)
    dots = "".join(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="{9 if i in (0, 1) else 8}" fill="#fff"/>'
                   for i, (sx, sy) in enumerate(stars))
    loose = "".join(f'<circle cx="{lx}" cy="{ly}" r="{lr}" fill="#fff" opacity="0.7"/>' for lx, ly, lr in LOOSE)
    ticks = "".join(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/>' for x1, y1, x2, y2 in (
        (CX, CY - R - 10, CX, CY - R - 26), (CX, CY + R + 10, CX, CY + R + 26),
        (CX - R - 10, CY, CX - R - 26, CY), (CX + R + 10, CY, CX + R + 26, CY)))
    mask = lambda name, dx, dy: (
        f'<mask id="{P}-{name}" maskUnits="userSpaceOnUse" x="0" y="0" width="1024" height="1024">'
        f'<g {turn}>{card} fill="#fff"/></g><g transform="translate({dx} {dy})"><g {turn}>{card} fill="#000"/></g></g></mask>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
<defs>
<linearGradient id="{P}-pl" x1="0.2" y1="0" x2="0.8" y2="1"><stop offset="0" stop-color="{PLATE[0]}"/><stop offset="1" stop-color="{PLATE[1]}"/></linearGradient>
<radialGradient id="{P}-plh" cx="0.26" cy="0.12" r="0.8"><stop offset="0" stop-color="#fff" stop-opacity="0.2"/><stop offset="0.55" stop-color="#fff" stop-opacity="0.05"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
<linearGradient id="{P}-rim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0.42"/><stop offset="0.1" stop-color="#fff" stop-opacity="0"/><stop offset="0.86" stop-color="{DARK}" stop-opacity="0"/><stop offset="1" stop-color="{DARK}" stop-opacity="0.35"/></linearGradient>
<clipPath id="{P}-clip"><rect x="82" y="82" width="860" height="860" rx="202"/></clipPath>
<filter id="{P}-amb" x="-50%" y="-50%" width="200%" height="200%" color-interpolation-filters="sRGB"><feGaussianBlur stdDeviation="56"/></filter>
<filter id="{P}-sh" x="-50%" y="-50%" width="200%" height="200%" color-interpolation-filters="sRGB"><feGaussianBlur stdDeviation="22"/></filter>
<filter id="{P}-hsoft" x="-50%" y="-50%" width="200%" height="200%" color-interpolation-filters="sRGB"><feGaussianBlur stdDeviation="2"/></filter>
<linearGradient id="{P}-obj" x1="0.1" y1="0.05" x2="0.9" y2="0.95"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#dfe7f2"/></linearGradient>
<linearGradient id="{P}-sky" x1="0.2" y1="0" x2="0.8" y2="1"><stop offset="0" stop-color="#28349a"/><stop offset="1" stop-color="#0f1552"/></linearGradient>
<clipPath id="{P}-chart"><circle cx="{CX}" cy="{CY}" r="{R}"/></clipPath>
{mask("hl", 7, 8.4)}
{mask("lo", -7, -8.4)}
</defs>
<g id="plate"><rect x="82" y="82" width="860" height="860" rx="202" fill="url(#{P}-pl)"/><rect x="82" y="82" width="860" height="860" rx="202" fill="url(#{P}-plh)"/></g>
<g id="ambient-shadow" clip-path="url(#{P}-clip)"><ellipse cx="520" cy="700" rx="320" ry="170" fill="{DARK}" opacity="0.38" filter="url(#{P}-amb)"/></g>
<g id="object-shadow" clip-path="url(#{P}-clip)"><g opacity="0.32" filter="url(#{P}-sh)" transform="translate(12 26)"><g {turn}>{card} fill="{DARK}"/></g></g></g>
<g id="object-main">
<g {turn}>
{card} fill="url(#{P}-obj)"/>
<circle cx="{CX}" cy="{CY}" r="{R}" fill="url(#{P}-sky)"/>
<g clip-path="url(#{P}-chart)" fill="none" stroke="#fff">
<circle cx="{CX}" cy="{CY}" r="{R * 0.62:.0f}" stroke-width="3" opacity="0.13"/>
<line x1="{CX - R}" y1="{CY}" x2="{CX + R}" y2="{CY}" stroke-width="3" opacity="0.1"/>
<line x1="{CX}" y1="{CY - R}" x2="{CX}" y2="{CY + R}" stroke-width="3" opacity="0.1"/>
</g>
<g clip-path="url(#{P}-chart)">{loose}<g fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round" opacity="0.45">{lines}</g>{dots}</g>
<g fill="none" stroke="{DARK}" stroke-width="7" stroke-linecap="round" opacity="0.32">{ticks}</g>
<g fill="none" stroke="{DARK}" stroke-width="12" stroke-linecap="round" opacity="0.16"><path d="M402 660H622"/><path d="M402 686H550"/></g>
</g>
<g filter="url(#{P}-hsoft)"><rect width="1024" height="1024" fill="#5a628c" opacity="0.25" mask="url(#{P}-lo)"/><rect width="1024" height="1024" fill="#fff" mask="url(#{P}-hl)"/></g>
</g>
<g id="plate-rim" clip-path="url(#{P}-clip)"><rect x="82" y="82" width="860" height="860" rx="202" fill="none" stroke="url(#{P}-rim)" stroke-width="8"/></g>
</svg>
'''
    with open(path, "w", encoding="utf-8") as out:
        out.write(svg)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "skymap.svg")
