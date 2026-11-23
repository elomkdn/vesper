#!/usr/bin/env python3
"""Vesper's icon in Luma's family style: a telescope on a night-indigo plate, aimed at a star.

Side-on, after Lucide's telescope (ISC): a white tube rising to the upper
right, a dew shield at its mouth, an eyepiece at the back and a small finder on
top, on a hub and tripod in a cooler grey. Lit from the upper left. The star it
is aimed at is the second object (it acts on the first, as the guide allows),
with a few faint pinpoints of sky around it.

Usage: python3 -I tools/make_icon_telescope.py out.svg   (an earlier design, kept for reference)
"""
import sys

P = "vsp"
PLATE = ("#4f5cf2", "#1e2499")      # a deeper indigo than usual: night
DARK = "#10155c"
THICK = 1.16                         # the tube's girth, for presence at small sizes
STAR = (792, 300, 46)                # on the tube's line, where it points
PINPOINTS = ((262, 250, 7, 0.75), (378, 190, 4.5, 0.6), (606, 206, 5, 0.65), (872, 470, 4.5, 0.55),
             (296, 384, 4, 0.5), (700, 548, 4, 0.45))
TILT = -26                     # degrees; the tube points up and to the right
PIVOT = (500, 452)             # the tube turns about this point, over the hub
HUB = (500, 486, 34)
FEET = ((392, 742), (612, 742))
REAR = (504, 712)


def tube_parts():
    """The tube, laid flat; the caller turns it. Centre line y = 452."""
    y = 452
    body = (f"M344 {y - 40}L652 {y - 56}Q664 {y - 56} 664 {y - 44}L664 {y + 44}Q664 {y + 56} 652 {y + 56}"
            f"L344 {y + 40}Q332 {y + 40} 332 {y + 28}L332 {y - 28}Q332 {y - 40} 344 {y - 40}Z")
    shield = f"M664 {y - 70}H704Q718 {y - 70} 718 {y - 56}V{y + 56}Q718 {y + 70} 704 {y + 70}H664Z"
    eyepiece = f"M296 {y - 22}H332V{y + 22}H296Q286 {y + 22} 286 {y + 12}V{y - 12}Q286 {y - 22} 296 {y - 22}Z"
    finder = f"M540 {y - 86}H612Q620 {y - 86} 620 {y - 78}V{y - 66}Q620 {y - 58} 612 {y - 58}H540Q532 {y - 58} 532 {y - 66}V{y - 78}Q532 {y - 86} 540 {y - 86}Z"
    stalk = f"M562 {y - 60}H574V{y - 46}H562Z"
    return body, shield, eyepiece, finder, stalk


def main(path):
    body, shield, eyepiece, finder, stalk = tube_parts()
    turn = (f'transform="rotate({TILT} {PIVOT[0]} {PIVOT[1]}) translate(0 {PIVOT[1]}) scale(1 {THICK}) '
            f'translate(0 {-PIVOT[1]})"')
    hx, hy, hr = HUB
    legs = "".join(f'<line x1="{hx}" y1="{hy}" x2="{x}" y2="{y}"/>' for x, y in FEET)
    rear = f'<line x1="{hx}" y1="{hy}" x2="{REAR[0]}" y2="{REAR[1]}"/>'
    tube = f'<path d="{body}"/><path d="{shield}"/><path d="{eyepiece}"/><path d="{finder}"/><path d="{stalk}"/>'

    def silhouette(fill):
        return (f'<g fill="none" stroke="{fill}" stroke-width="34" stroke-linecap="round">{legs}{rear}</g>'
                f'<circle cx="{hx}" cy="{hy}" r="{hr}" fill="{fill}"/><g fill="{fill}" {turn}>{tube}</g>')

    mask = lambda name, dx, dy: (
        f'<mask id="{P}-{name}" maskUnits="userSpaceOnUse" x="0" y="0" width="1024" height="1024">'
        f'<g fill="#fff" {turn}>{tube}</g>'
        f'<g transform="translate({dx} {dy})"><g fill="#000" {turn}>{tube}</g></g></mask>')
    y = 452
    detail = (f'<g {turn} fill="none" stroke="{DARK}" stroke-linecap="round">'
              f'<path d="M624 {y - 46}V{y + 46}" stroke-width="10" opacity="0.16"/>'
              f'<path d="M680 {y - 58}V{y + 58}" stroke-width="8" opacity="0.14"/>'
              f'<path d="M372 {y - 30}V{y + 30}" stroke-width="8" opacity="0.12"/></g>')
    sx, sy, sr = STAR
    k = sr * 0.16          # the sparkle's waist
    sparkle = (f"M{sx} {sy - sr}Q{sx + k} {sy - k} {sx + sr} {sy}Q{sx + k} {sy + k} {sx} {sy + sr}"
               f"Q{sx - k} {sy + k} {sx - sr} {sy}Q{sx - k} {sy - k} {sx} {sy - sr}Z")
    sky = (f'<g id="{P}-sky" clip-path="url(#{P}-clip)">'
           + "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#fff" opacity="{o}"/>' for x, y, r, o in PINPOINTS)
           + f'<circle cx="{sx}" cy="{sy}" r="{sr * 1.9:.0f}" fill="url(#{P}-glow)"/>'
           + f'<path d="{sparkle}" fill="url(#{P}-star)"/></g>')
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
<linearGradient id="{P}-mount" x1="0.1" y1="0" x2="0.9" y2="1"><stop offset="0" stop-color="#e9edf7"/><stop offset="1" stop-color="#b8c2da"/></linearGradient>
<radialGradient id="{P}-glow" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#fff6dc" stop-opacity="0.55"/><stop offset="1" stop-color="#fff6dc" stop-opacity="0"/></radialGradient>
<linearGradient id="{P}-star" x1="0.1" y1="0.05" x2="0.9" y2="0.95"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#fff1cf"/></linearGradient>
<linearGradient id="{P}-rear" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#c4cce2"/><stop offset="1" stop-color="#97a2c2"/></linearGradient>
{mask("hl", 7, 8.4)}
{mask("lo", -7, -8.4)}
</defs>
<g id="plate"><rect x="82" y="82" width="860" height="860" rx="202" fill="url(#{P}-pl)"/><rect x="82" y="82" width="860" height="860" rx="202" fill="url(#{P}-plh)"/></g>
{sky}
<g id="ambient-shadow" clip-path="url(#{P}-clip)"><ellipse cx="520" cy="700" rx="320" ry="170" fill="{DARK}" opacity="0.38" filter="url(#{P}-amb)"/></g>
<g id="object-shadow" clip-path="url(#{P}-clip)"><g opacity="0.32" filter="url(#{P}-sh)" transform="translate(12 26)">{silhouette(DARK)}</g></g>
<g id="object-main">
<g fill="none" stroke="url(#{P}-rear)" stroke-width="30" stroke-linecap="round">{rear}</g>
<g fill="none" stroke="url(#{P}-mount)" stroke-width="34" stroke-linecap="round">{legs}</g>
<circle cx="{hx}" cy="{hy}" r="{hr}" fill="url(#{P}-mount)"/>
<g fill="url(#{P}-obj)" {turn}>{tube}</g>
{detail}
<g filter="url(#{P}-hsoft)"><rect width="1024" height="1024" fill="#5a628c" opacity="0.25" mask="url(#{P}-lo)"/><rect width="1024" height="1024" fill="#fff" mask="url(#{P}-hl)"/></g>
</g>
<g id="plate-rim" clip-path="url(#{P}-clip)"><rect x="82" y="82" width="860" height="860" rx="202" fill="none" stroke="url(#{P}-rim)" stroke-width="8"/></g>
</svg>
'''
    with open(path, "w", encoding="utf-8") as out:
        out.write(svg)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "telescope.svg")
