"""Baseline: what you get by mechanically stripping the heavy site.

No judgement, no rewriting: drop video, images, scripts, styles and fonts,
keep every word that was on the everyday page. It is light, but is it right?
"""

from __future__ import annotations

import re

from .facts import ROOT

FULL = ROOT / "site" / "full" / "index.html"
STRIP = [
    r"<video[^>]*>.*?</video>",
    r"<script[^>]*>.*?</script>",
    r"<style[^>]*>.*?</style>",
    r"<link[^>]*>",
    r"<img[^>]*>",
]


def strip(html: str) -> str:
    for pattern in STRIP:
        html = re.sub(pattern, "", html, flags=re.S | re.I)
    return re.sub(r"\n\s*\n", "\n", html)


def baseline_page(hazard: str, level: int) -> str:
    """Same page for every hazard and level: stripping cannot know the situation."""
    return strip(FULL.read_text())
