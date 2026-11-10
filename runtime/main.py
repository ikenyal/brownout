"""AgentCore Runtime entrypoint for Brownout.

Payload: {"hazard": "flood" | "earthquake", "level": 1-5, "issued_at": ISO 8601 UTC (optional)}
  level 1-2 -> switch the site back to the full version (no agent needed)
  level 3-5 -> the agent rewrites the site; only a page that passed the guard
               is published, and only then does the edge switch to it.
An alert older than the one already live is ignored (see edge.set_level), so runs that
finish out of order, or Lambda's automatic retries, cannot roll the site back.
"""

from __future__ import annotations

import time

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from brownout.agent import brownout
from brownout.edge import get_level, is_stale, s3_publisher, set_level
from brownout.facts import HAZARDS

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload, context):
    hazard = payload.get("hazard", "flood")
    level = int(payload.get("level", 1))
    if hazard not in HAZARDS or not 1 <= level <= 5:
        return {"ok": False, "error": f"bad payload: {payload}"}
    issued_at = payload.get("issued_at")
    start = time.time()
    previous = get_level()
    if is_stale(issued_at):  # cheap check first: skip the agent entirely for an old alert
        return {"ok": False, "stale": True, "level": level, "previous": previous}
    if level <= 2:
        if not set_level(level, issued_at):
            return {"ok": False, "stale": True, "level": level, "previous": previous}
        return {"ok": True, "mode": "full", "level": level, "previous": previous,
                "seconds": round(time.time() - start, 1)}
    log = brownout(hazard, level, s3_publisher())
    if log.published is None:
        # Keep whatever is live now; never switch to an unchecked page.
        return {"ok": False, "level": level, "previous": previous, "attempts": log.attempts,
                "feedback": log.feedback, "seconds": round(time.time() - start, 1)}
    if not set_level(level, issued_at):  # a newer alert won while the agent was working
        return {"ok": False, "stale": True, "level": level, "previous": previous,
                "seconds": round(time.time() - start, 1)}
    return {"ok": True, "mode": f"level-{level}", "level": level, "previous": previous,
            "attempts": log.attempts, "feedback": log.feedback, "seconds": round(time.time() - start, 1)}


if __name__ == "__main__":
    app.run()
