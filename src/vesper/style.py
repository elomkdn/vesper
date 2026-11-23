# SPDX-License-Identifier: GPL-3.0-or-later
"""Vesper's own styles, for its own content only: the time wheels, after Luma's Clock.

Every rule sits under the `vesper-` prefix, every colour is a Luma token and
the text sizes come from LumaUI's type roles. LumaUI's parts are never restyled.
"""
from __future__ import annotations

CSS = """
.vesper-wheels { min-height: 200px; }
.vesper-wheel-band {
  margin: 0 12px; border-radius: var(--lumaui-inset-radius);
  background: @luma_well; box-shadow: inset 0 0 0 1px @luma_well_ring;
}
.vesper-wheel { min-width: 76px; }
.vesper-wheel:focus-visible { outline: 2px solid @luma_focus_ring; outline-offset: -2px; border-radius: var(--lumaui-inset-radius); }
.vesper-wheel-item { font-weight: 400; font-feature-settings: "tnum"; color: @luma_muted; }
.vesper-wheel-item.on { font-weight: 600; color: @luma_ink; }
.vesper-wheel-item.near { opacity: 0.7; }
.vesper-wheel-item.far { opacity: 0.3; }
.vesper-wheel-colon { font-weight: 300; color: @luma_ink; }
"""


def install() -> None:
    """Through LumaUI's own loader, so the styles follow the treatment (dark, high contrast) live."""
    from luma_appkit import add_style_builder
    add_style_builder(lambda _appearance: CSS)
