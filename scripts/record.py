"""Record phone-sized clips for the demo video (Playwright video, 390x844).

  full      - scroll through the heavy everyday site (local files)
  throttled - load the heavy site over emulated congested 3G (local server)
  live      - watch the LIVE CloudFront URL while alerts 4 -> 5 -> 1 are sent
Run:  PYTHONPATH=. uv run python scripts/record.py full|throttled|live
"""

from __future__ import annotations

import functools
import http.server
import json
import shutil
import sys
import threading
import time
from pathlib import Path

import boto3
from playwright.sync_api import sync_playwright

from brownout.edge import config

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "video"
VIEW = {"width": 390, "height": 844}
BADGE = """(t) => { let b = document.getElementById('__badge'); if (!b) { b = document.createElement('div'); b.id='__badge';
 b.style.cssText='position:fixed;bottom:12px;left:12px;right:12px;z-index:99999;background:#111d;color:#fff;font:600 15px/1.4 system-ui;padding:8px 12px;border-radius:10px';
 document.body.appendChild(b);} b.textContent = t; }"""


def record(name: str, fn) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport=VIEW, device_scale_factor=2, record_video_dir=str(OUT / "tmp"),
                                  record_video_size={"width": 780, "height": 1688})  # page fills the top-left quarter; assemble_video.py crops it
        page = ctx.new_page()
        fn(page, ctx)
        video = page.video.path()
        ctx.close()
        browser.close()
    shutil.move(video, OUT / f"{name}.webm")
    shutil.rmtree(OUT / "tmp", ignore_errors=True)
    print("saved", OUT / f"{name}.webm")


def full(page, ctx) -> None:
    page.goto((ROOT / "site/full/index.html").as_uri())
    page.wait_for_timeout(3000)
    for _ in range(14):
        page.mouse.wheel(0, 500)
        page.wait_for_timeout(700)
    page.wait_for_timeout(1500)


def throttled(page, ctx) -> None:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    handler.log_message = lambda *a: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    cdp = ctx.new_cdp_session(page)
    cdp.send("Network.enable")
    cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
    cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 400,
             "downloadThroughput": 400 * 1000 / 8, "uploadThroughput": 400 * 1000 / 8})
    t0 = time.time()
    page.goto(f"http://127.0.0.1:{httpd.server_address[1]}/site/full/index.html", wait_until="commit")
    while time.time() - t0 < 30:
        try:
            page.evaluate(BADGE, f"Congested 3G - full site - loading... {time.time() - t0:.0f}s")
        except Exception:
            pass
        page.wait_for_timeout(500)
    httpd.shutdown()


def heading(page) -> str:
    try:
        return page.eval_on_selector("h1", "e => e.textContent") or "(full site)"
    except Exception:
        return "(full site)"


def live(page, ctx) -> None:
    url = f"https://{config()['domain']}/"
    events = boto3.client("events", region_name="us-east-1")
    page.goto(f"{url}?t={time.time()}")
    page.wait_for_timeout(2000)
    for hazard, level in [("flood", 4), ("flood", 5), ("flood", 1)]:
        before = heading(page)
        events.put_events(Entries=[{"Source": "examplecity.alerts", "DetailType": "AlertLevelChanged",
                                    "Detail": json.dumps({"hazard": hazard, "level": level})}])
        t0 = time.time()
        label = f"Alert sent: {hazard}, Level {level}" if level >= 3 else "All clear: Level 1"
        while time.time() - t0 < 150:
            page.evaluate(BADGE, f"{label} - {time.time() - t0:.0f}s")
            page.wait_for_timeout(2000)
            page.goto(f"{url}?t={time.time()}")
            if heading(page) != before:
                page.evaluate(BADGE, f"{label} - live after {time.time() - t0:.0f}s")
                page.wait_for_timeout(4000)
                break


if __name__ == "__main__":
    mode = sys.argv[1]
    record(mode, {"full": full, "throttled": throttled, "live": live}[mode])
