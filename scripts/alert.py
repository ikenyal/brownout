"""Raise or lower the (simulated) alert, and time how long until the live site changes.

Usage:  uv run python scripts/alert.py flood 5
        uv run python scripts/alert.py flood 1      # back to normal
        uv run python scripts/alert.py flood 4 --issued-ago 120 --timeout 90
            # a late, older alert (as if a run had been retried): the site must NOT change
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
import urllib.request

import boto3

from brownout.edge import EVENT_SOURCE, config


def live_heading(url: str) -> str:
    html = urllib.request.urlopen(f"{url}?t={time.time()}").read().decode("utf-8", "ignore")
    start = html.find("<h1")
    return html[html.find(">", start) + 1: html.find("</h1>", start)] if start >= 0 else "(full site)"


def main(hazard: str, level: int, issued_ago: int = 0, timeout: int = 180) -> None:
    url = f"https://{config()['domain']}/"
    events = boto3.client("events", region_name="us-east-1")
    before = live_heading(url)
    t0 = time.time()
    entry = {"Source": EVENT_SOURCE, "DetailType": "AlertLevelChanged",
             "Detail": json.dumps({"hazard": hazard, "level": level})}
    if issued_ago:
        entry["Time"] = datetime.now(timezone.utc) - timedelta(seconds=issued_ago)
    events.put_events(Entries=[entry])
    print(f"event sent: {hazard} level {level}"
          f"{f' issued {issued_ago}s ago' if issued_ago else ''} (live now: {before})")
    while time.time() - t0 < timeout:
        time.sleep(2)
        now = live_heading(url)
        if now != before:
            print(f"live after {time.time() - t0:.1f}s: {now}")
            return
    print(f"no change within {timeout}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("hazard", choices=["flood", "earthquake"])
    ap.add_argument("level", type=int, choices=range(1, 6))
    ap.add_argument("--issued-ago", type=int, default=0, help="backdate the alert by N seconds")
    ap.add_argument("--timeout", type=int, default=180)
    a = ap.parse_args()
    main(a.hazard, a.level, a.issued_ago, a.timeout)
