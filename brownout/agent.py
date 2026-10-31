"""The Brownout agent: rewrite the city site for the current alert level.

Two agents and one deterministic guard:
  Curator  (specialist agent, called as a tool) decides WHAT must stay.
  Writer   (main agent) writes the page and calls publish_page.
  PublishGuard (a hook) blocks publish_page until the page fits the
  byte budget and keeps every required fact - the model cannot talk its way past them.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from strands import Agent, tool
from strands.hooks import BeforeInvocationEvent, BeforeToolCallEvent, HookProvider, HookRegistry
from strands.models import BedrockModel

from .facts import TOWN, budget, check, describe

MODEL_ID = os.environ.get("BROWNOUT_MODEL", "us.amazon.nova-2-lite-v1:0")
MAX_PUBLISH_ATTEMPTS = 4

CURATOR_PROMPT = """You are the Curator for Example City's emergency website.
Given a hazard and an alert level, decide which facts from the city data people
need RIGHT NOW, in priority order. Rules:
- Use only facts from the data. Never invent anything.
- Exclude every shelter that is not safe for this hazard (check 'safe_for' and 'notes').
- Everyday notices (festivals, tax, garbage, library...) never belong in an emergency page.
- Higher level = fewer words. At Level 5 keep only what saves a life in the next minutes.
Answer with a short brief: the action for this level, the hotlines, the shelters
(name + address), water points if relevant, and what to leave out."""

WRITER_PROMPT = """You are Brownout, the agent that keeps Example City's website usable during a disaster.
Steps: 1) call read_town_facts, 2) call curate for a brief, 3) write ONE self-contained HTML page,
4) call publish_page with it. If publish_page is refused, fix exactly what the message says and try again.
Page rules:
- Include <meta name="viewport" content="width=device-width, initial-scale=1">.
- English, short plain sentences, the most urgent action first, a big heading with the alert level text (e.g. 'Level 4 - Evacuate').
- Phone numbers as tel: links. Only facts from read_town_facts.
- No images, no JavaScript, no web fonts, no external files. A few lines of inline CSS at most.
- Stay far below the byte budget you are given; Level 5 must fit in the first network round trip."""


@dataclass
class RunLog:
    attempts: int = 0
    feedback: list[str] = field(default_factory=list)
    published: str | None = None


class PublishGuard(HookProvider):
    """Deterministic gate in front of publish_page: attempt limit, byte budget, required facts."""

    def __init__(self, hazard: str, level: int, log: RunLog):
        self.hazard, self.level, self.log = hazard, level, log

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeToolCallEvent, self.guard)

    def guard(self, event: BeforeToolCallEvent) -> None:
        if event.tool_use["name"] != "publish_page":
            return
        self.log.attempts += 1
        if self.log.attempts > MAX_PUBLISH_ATTEMPTS:
            event.cancel_tool = "Publish attempt limit reached. Stop and report the problem."
            return
        html = event.tool_use["input"].get("html", "")
        result = check(html, self.hazard, self.level)
        if not result.passed:
            msg = describe(result)
            self.log.feedback.append(msg)
            event.cancel_tool = f"Refused, page not published. {msg}"


def build_agent(hazard: str, level: int, publisher: Callable[[int, str], str], log: RunLog, guard: bool = True) -> Agent:
    model = BedrockModel(model_id=MODEL_ID, region_name="us-east-1")
    curator = Agent(model=model, system_prompt=CURATOR_PROMPT, callback_handler=None)

    @tool
    def read_town_facts() -> str:
        """Return the official Example City data (the only allowed source of facts)."""
        return json.dumps(TOWN)

    @tool
    def curate(hazard: str, level: int) -> str:
        """Ask the Curator which facts must stay on the page for this hazard and alert level.

        Args:
            hazard: 'flood' or 'earthquake'
            level: alert level 3, 4 or 5
        """
        return str(curator(f"Hazard: {hazard}. Alert level: {level}.\nCity data:\n{json.dumps(TOWN)}"))

    @tool
    def publish_page(html: str) -> str:
        """Publish the emergency page. Refused unless it fits the budget and keeps every required fact.

        Args:
            html: the complete, self-contained HTML document
        """
        if not guard:
            log.attempts += 1
        log.published = html
        return publisher(level, html)

    return Agent(
        model=model,
        system_prompt=WRITER_PROMPT,
        tools=[read_town_facts, curate, publish_page],
        hooks=[PublishGuard(hazard, level, log)] if guard else [],
        callback_handler=None,
    )


def brownout(hazard: str, level: int, publisher: Callable[[int, str], str], guard: bool = True) -> RunLog:
    log = RunLog()
    agent = build_agent(hazard, level, publisher, log, guard)
    agent(
        f"Alert: {hazard}, Level {level}. Byte budget for this page: {budget(level):,} bytes gzipped. "
        "Rewrite the site for this situation and publish it."
    )
    return log


def local_publisher(out_dir: Path) -> Callable[[int, str], str]:
    def publish(level: int, html: str) -> str:
        target = out_dir / f"level-{level}" / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html)
        return f"Published to {target}"
    return publish
