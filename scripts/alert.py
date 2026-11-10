"""Raise or lower the (simulated) alert, and time how long until the live site changes.

Usage:  uv run python scripts/alert.py flood 5
        uv run python scripts/alert.py flood 1      # back to normal
        uv run python scripts/alert.py flood 4 --issued-ago 120 --timeout 90
            # a late, older alert (as if a run had been retried): the site must NOT change

Right after a switch, some requests can still get the old page for a while (the new
KeyValueStore value does not reach every edge server at the same instant). So this prints two times: when the
new page was first seen, and when it was seen on --stable consecutive reads (default 5).
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
import urllib.request

import boto3

from brownout.edge import EVENT_SOURCE, config


def live_heading(url: str) -> str:
    html = urllib.request.urlopen(f"{url}?t={time.time()}").read().decode("utf-8", "ignore")
    start = html.find("<h1")
    return html[html.find(">", start) + 1: html.find("</h1>", start)] if start >= 0 else "(full site)"


def settled_heading(url: str, reads: int = 5) -> str:
    """The heading most reads agree on. Right after a switch, different edge servers can
    still answer with the old page for a while, so one read is not enough."""
    seen = []
    for _ in range(reads):
        seen.append(live_heading(url))
        time.sleep(1)
    return Counter(seen).most_common(1)[0][0]


def main(hazard: str, level: int, issued_ago: int = 0, timeout: int = 180, stable: int = 5) -> None:
    """Report two times: when the new page was first seen, and when it was seen on
    `stable` consecutive reads (2 s apart) with no old page in between."""
    url = f"https://{config()['domain']}/"
    events = boto3.client("events", region_name="us-east-1")
    before = settled_heading(url)
    t0 = time.time()
    entry = {"Source": EVENT_SOURCE, "DetailType": "AlertLevelChanged",
             "Detail": json.dumps({"hazard": hazard, "level": level})}
    if issued_ago:
        entry["Time"] = datetime.now(timezone.utc) - timedelta(seconds=issued_ago)
    events.put_events(Entries=[entry])
    print(f"event sent: {hazard} level {level}"
          f"{f' issued {issued_ago}s ago' if issued_ago else ''} (live now: {before})")
    first = target = None
    streak = flaps = 0
    while time.time() - t0 < timeout:
        time.sleep(2)
        now = live_heading(url)
        if now == before:
            if first is not None:
                flaps += 1  # an edge server still answered with the old page
            streak = 0
            continue
        if first is None:
            first, target = time.time() - t0, now
        streak = streak + 1 if now == target else 1
        if streak >= stable:
            print(f"live after {first:.1f}s (first seen), {time.time() - t0:.1f}s (stable): {now}"
                  f" [old page seen {flaps} time(s) in between]")
            return
    if first is None:
        print(f"no change within {timeout}s")
    else:
        print(f"first seen after {first:.1f}s but not stable within {timeout}s: {target} [old page seen {flaps} time(s)]")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("hazard", choices=["flood", "earthquake"])
    ap.add_argument("level", type=int, choices=range(1, 6))
    ap.add_argument("--issued-ago", type=int, default=0, help="backdate the alert by N seconds")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--stable", type=int, default=5, help="consecutive reads that must show the new page")
    a = ap.parse_args()
    main(a.hazard, a.level, a.issued_ago, a.timeout, a.stable)
