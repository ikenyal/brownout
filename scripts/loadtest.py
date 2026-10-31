"""Load the full site and the Brownout pages over a throttled network, like a phone in a disaster area.

Serves the pages locally and uses Chrome DevTools network emulation, so the numbers
are about bytes and round trips, not about any particular server.
Run:  uv run python scripts/loadtest.py
"""

from __future__ import annotations

import functools
import http.server
import json
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {
    # name: (download kbit/s, upload kbit/s, round-trip latency ms)
    "3G (congested)": (400, 400, 400),
    "2G": (50, 20, 500),
}
PAGES = {
    "full site": "site/full/index.html",
    "Level 3 (flood)": "out/eval/brownout/flood/t0/level-3/index.html",
    "Level 4 (flood)": "out/eval/brownout/flood/t0/level-4/index.html",
    "Level 5 (flood)": "out/eval/brownout/flood/t0/level-5/index.html",
}
TIMEOUT_S = 180


def serve() -> int:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    handler.log_message = lambda *a: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd.server_address[1]


def measure(browser, url: str, down: int, up: int, rtt: int) -> dict:
    ctx = browser.new_context()
    page = ctx.new_page()
    cdp = ctx.new_cdp_session(page)
    cdp.send("Network.enable")
    cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
    cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": rtt,
             "downloadThroughput": down * 1000 / 8, "uploadThroughput": up * 1000 / 8})
    t0 = time.time()
    result = {}
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_S * 1000)
        result["first_content_s"] = round(time.time() - t0, 1)
        page.wait_for_load_state("load", timeout=max(1, TIMEOUT_S * 1000 - int((time.time() - t0) * 1000)))
        result["fully_loaded_s"] = round(time.time() - t0, 1)
    except Exception:
        result.setdefault("first_content_s", None)
        result["fully_loaded_s"] = None  # did not finish within TIMEOUT_S
    ctx.close()
    return result


def main() -> None:
    port = serve()
    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for prof, (down, up, rtt) in PROFILES.items():
            for name, path in PAGES.items():
                r = measure(browser, f"http://127.0.0.1:{port}/{path}", down, up, rtt)
                rows.append({"network": prof, "page": name, **r})
                print(json.dumps(rows[-1]))
        browser.close()
    out = ROOT / "results" / "loadtest.json"
    out.write_text(json.dumps(rows, indent=2))
    print(f"\n{'network':<16} {'page':<18} {'first content':>14} {'fully loaded':>14}")
    for r in rows:
        f = lambda v: f"{v}s" if v is not None else f">{TIMEOUT_S}s"
        print(f"{r['network']:<16} {r['page']:<18} {f(r['first_content_s']):>14} {f(r['fully_loaded_s']):>14}")


if __name__ == "__main__":
    main()
