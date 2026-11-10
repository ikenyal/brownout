"""A page built by plain code from the city data: the floor under the agent.

If the agent cannot produce a page that passes PublishGuard (it gives up after six
refusals), the runtime publishes this instead of leaving the full site up during an
alert. It contains exactly the items content/must_have.json requires for the hazard and
level, copied from content/town.json, so it passes the same checks by construction.
It is plainer than the agent's page, and that is the point: it cannot be wrong in new ways.
"""

from __future__ import annotations

from html import escape

from brownout.facts import MUST, TOWN


def _by_id(items: list[dict], ids: list[str]) -> list[dict]:
    return [x for x in items if x["id"] in ids]


def fallback_page(hazard: str, level: int) -> str:
    required = MUST[hazard][str(level)]["required"]
    ids = {kind: [i.split(":")[1] for i in required if i.startswith(kind + ":")]
           for kind in ("hotline", "shelter", "water")}
    alert = TOWN["alert_levels"][str(level)]
    parts = [
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        f"<title>Example City - {escape(hazard.title())} Alert {escape(alert['label'])}</title>",
        "<style>body{font-family:sans-serif;margin:1em;line-height:1.5}h1{color:#b00}</style></head><body>",
        f"<h1>{escape(alert['label'])}</h1>",
        f"<p><strong>Action:</strong> {escape(alert['action'])}</p>",
    ]
    hotlines = _by_id(TOWN["hotlines"], ids["hotline"])
    if hotlines:
        parts.append("<h2>Hotlines</h2><ul>")
        parts += [f"<li><a href=\"tel:{h['phone']}\">{h['phone']}</a> - {escape(h['name'])}</li>" for h in hotlines]
        parts.append("</ul>")
    shelters = _by_id(TOWN["shelters"], ids["shelter"])
    if shelters:
        parts.append("<h2>Safe Shelters</h2><ul>")
        parts += [f"<li><strong>{escape(s['name'])}</strong>, {escape(s['address'])}</li>" for s in shelters]
        parts.append("</ul>")
    water = _by_id(TOWN["water_points"], ids["water"])
    if water:
        parts.append("<h2>Water Points</h2><ul>")
        parts += [f"<li>{escape(w['name'])}, {escape(w['address'])}</li>" for w in water]
        parts.append("</ul>")
    parts.append("</body></html>")
    return "\n".join(parts)
