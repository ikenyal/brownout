"""AgentCore Runtime entrypoint for Brownout.

Payload: {"hazard": "flood" | "earthquake", "level": 1-5, "issued_at": ISO 8601 UTC (optional)}
  level 1-2 -> switch the site back to the full version.
  level 3-5 -> 1. publish the template page built by code from the city data (brownout/template.py),
                  after the deterministic checks, and switch the edge to it. This is the fast,
                  guaranteed path: no model call stands between the alert and the switch.
               2. then let the agent try to write a better page. PublishGuard only lets it
                  publish a page that passes the same checks (and the Verifier); if it does,
                  that page replaces the template at the same address. If it gives up, the
                  template simply stays live.
Set BROWNOUT_AGENT=off to run with the template only.
An alert older than the one already live is ignored (see edge.set_level), so runs that
finish out of order, or Lambda's automatic retries, cannot roll the site back.
"""

from __future__ import annotations

import os
import time

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from brownout.edge import get_level, is_stale, s3_publisher, set_level
from brownout.facts import HAZARDS, check
from brownout.template import template_page

app = BedrockAgentCoreApp()
AGENT_ON = os.environ.get("BROWNOUT_AGENT", "on").lower() != "off"


@app.entrypoint
def invoke(payload, context):
    hazard = payload.get("hazard", "flood")
    level = int(payload.get("level", 1))
    if hazard not in HAZARDS or not 1 <= level <= 5:
        return {"ok": False, "error": f"bad payload: {payload}"}
    issued_at = payload.get("issued_at")
    start = time.time()
    previous = get_level()
    if is_stale(issued_at):  # an older alert than the one already live: do nothing
        return {"ok": False, "stale": True, "level": level, "previous": previous}
    if level <= 2:
        if not set_level(level, issued_at):
            return {"ok": False, "stale": True, "level": level, "previous": previous}
        return {"ok": True, "mode": "full", "level": level, "previous": previous,
                "seconds": round(time.time() - start, 1)}

    # 1. The template goes live first.
    publish = s3_publisher()
    html = template_page(hazard, level)
    if not check(html, hazard, level).passed:  # cannot happen with valid data; never publish unchecked
        return {"ok": False, "error": "template failed the checks", "level": level, "previous": previous}
    publish(level, html)
    if not set_level(level, issued_at):  # a newer alert is already live
        return {"ok": False, "stale": True, "level": level, "previous": previous}
    result = {"ok": True, "mode": f"template-level-{level}", "level": level, "previous": previous,
              "switched_after": round(time.time() - start, 1)}
    if not AGENT_ON:
        return result

    # 2. The agent may replace the template with a better page that passes the same checks.
    from brownout.agent import brownout  # imported here so a template-only runtime never loads the model stack
    log = brownout(hazard, level, publish)
    if log.published is not None:
        result["mode"] = f"agent-level-{level}"
    result.update(attempts=log.attempts, feedback=log.feedback, seconds=round(time.time() - start, 1))
    return result


if __name__ == "__main__":
    app.run()
