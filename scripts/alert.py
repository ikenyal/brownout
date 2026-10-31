"""Raise or lower the (simulated) alert, and time how long until the live site changes.

Usage:  uv run python scripts/alert.py flood 5
        uv run python scripts/alert.py flood 1      # back to normal
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request

import boto3

from brownout.edge import config


def live_heading(url: str) -> str:
    html = urllib.request.urlopen(f"{url}?t={time.time()}").read().decode("utf-8", "ignore")
    start = html.find("<h1")
    return html[html.find(">", start) + 1: html.find("</h1>", start)] if start >= 0 else "(full site)"


def main(hazard: str, level: int) -> None:
    url = f"https://{config()['domain']}/"
    events = boto3.client("events", region_name="us-east-1")
    before = live_heading(url)
    t0 = time.time()
    events.put_events(Entries=[{"Source": "examplecity.alerts", "DetailType": "AlertLevelChanged",
                                "Detail": json.dumps({"hazard": hazard, "level": level})}])
    print(f"event sent: {hazard} level {level} (live now: {before})")
    while time.time() - t0 < 180:
        time.sleep(2)
        now = live_heading(url)
        if now != before:
            print(f"live after {time.time() - t0:.1f}s: {now}")
            return
    print("no change within 180s")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))
