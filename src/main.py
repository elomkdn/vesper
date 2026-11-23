#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
import os
import sys
from pathlib import Path

# A night sky stays dark: a light bar over the stars would glare and spoil dark-adapted eyes.
# LumaUI's own opt-out for apps with a fixed look; it leaves the desktop's setting alone.
os.environ.setdefault("LUMA_APPKIT_FIXED_DARK", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vesper.window import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
