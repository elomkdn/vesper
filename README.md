# Vesper

The sky above you, right now. A Luma app built with LumaUI.

Vesper draws the sky over where you are: 5,044 naked-eye stars in their true
colours, the constellations, the Milky Way, the planets and the Moon in its real
phase, exactly as they stand at this moment.

- Drag to look around, pinch or scroll to zoom, tap anything to learn what it is
- **Time**: tap the time and turn the hour and minute wheels, step to the night
  before or after, or jump to dusk, midnight or dawn
- **Tonight**: what is worth seeing tonight, and when; a tap takes you there
- **Find**: any planet, named star or constellation
- **Where**: use your location (asked once, through the system's Location
  portal) or pick from 34,000 cities; times follow the place you look from
- Works offline: no account, and nothing Vesper knows leaves the device
- Always dark, so a light desktop never glares over the stars

One app on a phone, a tablet and a desktop. The sky is Vesper's only drawn
content; everything around it is LumaUI (AppWindow, Island, ActionCenter,
CornerPill, DetailsPane, EmptyState, FactRow, Sparkline, panels and toasts), and the sky itself is
painted with LumaUI's own sky colour tokens.

## Run

On Luma, from the source tree:

```sh
./run-app
```

Check runs: `APP_WIDTH=360 APP_SHOT=/tmp/shot.png ./run-app` renders the window
and quits. `VESPER_PLACE=Paris` and `VESPER_TIME=2026-11-23T21:00:00+00:00`
pick a place and a moment.

## Build

```sh
flatpak-builder --user --install --install-deps-from=luma build-dir flatpak/io.github.elomkdn.Vesper.json
```

`luma lint` and `luma test` pass.

## Data

- Stars, constellation figures and the Milky Way: [d3-celestial](https://github.com/ofrohn/d3-celestial)
  by Olaf Frohn (BSD-3-Clause), compacted by `tools/build_catalog.py`
- Planet, Moon and Sun positions: [Astronomy Engine](https://github.com/cosinekitty/astronomy)
  by Don Cross (MIT), vendored as `src/vesper/astronomy.py`
- Cities: [GeoNames](https://www.geonames.org) (CC BY 4.0), built by `tools/build_cities.py`

## License

GPL-3.0-or-later. Third-party licences are in `LICENSES/`.
