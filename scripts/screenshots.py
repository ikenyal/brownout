"""Phone-sized screenshots of the full site and the Brownout pages (for the article and the video)."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "img"
SHOTS = {
    "full-top": ("site/full/index.html", None),
    "full-safety": ("site/full/index.html", "#safety"),
    "flood-level-3": ("out/eval/brownout/flood/t0/level-3/index.html", None),
    "flood-level-4": ("out/eval/brownout/flood/t0/level-4/index.html", None),
    "flood-level-5": ("out/eval/brownout/flood/t0/level-5/index.html", None),
    "baseline-stripped": ("out/baseline.html", None),
}


def main() -> None:
    from brownout.baseline import baseline_page
    (ROOT / "out").mkdir(exist_ok=True)
    (ROOT / "out" / "baseline.html").write_text(baseline_page("flood", 4))
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        for name, (path, anchor) in SHOTS.items():
            page.goto((ROOT / path).as_uri() + (anchor or ""))
            page.wait_for_timeout(1500)
            page.screenshot(path=str(OUT / f"{name}.png"))
        browser.close()
    print("saved to", OUT)


if __name__ == "__main__":
    main()
