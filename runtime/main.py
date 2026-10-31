"""AgentCore Runtime entrypoint for Brownout.

Payload: {"hazard": "flood" | "earthquake", "level": 1-5}
  level 1-2 -> switch the site back to the full version (no agent needed)
  level 3-5 -> the agent rewrites the site; only a page that passed the guard
               is published, and only then does the edge switch to it.
"""

from __future__ import annotations

import time

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from brownout.agent import brownout
from brownout.edge import get_level, s3_publisher, set_level
from brownout.facts import HAZARDS

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload, context):
    hazard = payload.get("hazard", "flood")
    level = int(payload.get("level", 1))
    if hazard not in HAZARDS or not 1 <= level <= 5:
        return {"ok": False, "error": f"bad payload: {payload}"}
    start = time.time()
    previous = get_level()
    if level <= 2:
        set_level(level)
        return {"ok": True, "mode": "full", "level": level, "previous": previous,
                "seconds": round(time.time() - start, 1)}
    log = brownout(hazard, level, s3_publisher())
    if log.published is None:
        # Keep whatever is live now; never switch to an unchecked page.
        return {"ok": False, "level": level, "previous": previous, "attempts": log.attempts,
                "feedback": log.feedback, "seconds": round(time.time() - start, 1)}
    set_level(level)
    return {"ok": True, "mode": f"level-{level}", "level": level, "previous": previous,
            "attempts": log.attempts, "feedback": log.feedback, "seconds": round(time.time() - start, 1)}


if __name__ == "__main__":
    app.run()
