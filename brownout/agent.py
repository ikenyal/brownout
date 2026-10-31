"""The Brownout agent: rewrite the city site for the current alert level.

Two agents and one deterministic guard:
  Curator  (specialist agent, called as a tool) decides WHAT must stay.
  Writer   (main agent) writes the page and calls publish_page.
  Verifier (third agent, inside the guard) flags any sentence the city data does not support.
  PublishGuard (a hook) blocks publish_page until the page fits the
  byte budget and keeps every required fact - the model cannot talk its way past them.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from strands import Agent, tool
from strands.hooks import BeforeInvocationEvent, BeforeToolCallEvent, HookProvider, HookRegistry
from strands.models import BedrockModel

from .facts import TOWN, budget, check, describe

MODEL_ID = os.environ.get("BROWNOUT_MODEL", "us.amazon.nova-2-lite-v1:0")
MAX_PUBLISH_ATTEMPTS = 6

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
- Phone numbers as tel: links whose visible text is just the number (e.g. <a href="tel:000-0000-0001">000-0000-0001</a>). Only facts from read_town_facts: no extra advice, tips or claims of your own, not even general safety tips.
- Never mention what you left out (no "leave out" or "ignore the festival" notes): people only see what matters.
- No images, no JavaScript, no web fonts, no external files. A few lines of inline CSS at most.
- Stay far below the byte budget you are given; Level 5 must fit in the first network round trip."""


VERIFIER_PROMPT = """You check an emergency web page against the official city data.
List every sentence or phrase on the page that states a fact, gives advice or makes a claim
that is NOT in the data. Rewording, shortening or combining things that ARE in the data is fine, and so is adding a word like "now" or "to a shelter" when the data says the same. Before you flag anything, look for the same meaning in the data; flag it only if the data says nothing like it.
Headings, section labels, the city name, the alert level label and link text are fine.
Answer with JSON only: {"unsupported": ["exact sentence from the page", ...]} - an empty list if all is supported."""


def unsupported_sentences(verifier: Agent, html: str) -> list[str]:
    text = re.sub(r"\s+", " ", re.sub(r"<(style|script)[^>]*>.*?</\1>|<[^>]+>", " ", html, flags=re.S)).strip()
    verifier.messages = []  # judge each page on its own
    answer = str(verifier(f"City data:\n{json.dumps(TOWN)}\n\nPage text:\n{text}"))
    match = re.search(r"\{.*\}", answer, re.S)
    try:
        items = json.loads(match.group(0)).get("unsupported", []) if match else []
    except json.JSONDecodeError:
        return []
    flagged = [i for i in items if isinstance(i, str) and i.strip()]
    return [i for i in flagged if not close_to_data(i)]


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _records() -> list[str]:
    """One string per thing in the data (a shelter with its address and notes, a hotline, a level...)."""
    out = [json.dumps(TOWN["town"])]
    out += [json.dumps(v) for v in TOWN["alert_levels"].values()]
    for key in ("hotlines", "shelters", "water_points", "everyday_notices"):
        out += [json.dumps(r) for r in TOWN[key]]
    return out


DATA_STRINGS = _records()


def close_to_data(sentence: str, threshold: float = 0.6) -> bool:
    """Deterministic second opinion: drop a flag if most of its words come from one data string.
    Keeps the LLM judge from blocking honest paraphrases."""
    words = _words(sentence)
    if len(words) <= 6:
        return True  # headings and labels

    return max(len(words & _words(d)) / len(words) for d in DATA_STRINGS) >= threshold


@dataclass
class RunLog:
    attempts: int = 0
    feedback: list[str] = field(default_factory=list)
    published: str | None = None
    verifier_flags: int = 0


class PublishGuard(HookProvider):
    """Deterministic gate in front of publish_page: attempt limit, byte budget, required facts."""

    def __init__(self, hazard: str, level: int, log: RunLog, verifier: Agent | None = None):
        self.hazard, self.level, self.log, self.verifier = hazard, level, log, verifier

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
        if result.passed and self.verifier is not None:
            result.unsupported = unsupported_sentences(self.verifier, html)
            self.log.verifier_flags += len(result.unsupported)
        if not result.passed:
            msg = describe(result)
            self.log.feedback.append(msg)
            event.cancel_tool = f"Refused, page not published. {msg}"


def build_agent(hazard: str, level: int, publisher: Callable[[int, str], str], log: RunLog, guard: bool = True) -> Agent:
    model = BedrockModel(model_id=MODEL_ID, region_name="us-east-1")
    curator = Agent(model=model, system_prompt=CURATOR_PROMPT, callback_handler=None)
    verifier = Agent(model=model, system_prompt=VERIFIER_PROMPT, callback_handler=None)

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
        hooks=[PublishGuard(hazard, level, log, verifier)] if guard else [],
        callback_handler=None,
    )


def brownout(hazard: str, level: int, publisher: Callable[[int, str], str], guard: bool = True) -> RunLog:
    log = RunLog()
    agent = build_agent(hazard, level, publisher, log, guard)
    agent(
        f"Alert: {hazard}, Level {level}. Byte budget for this page: {budget(level):,} bytes gzipped. "
        "Rewrite the site for this situation and publish it."
    )
    if log.published is None and log.attempts < MAX_PUBLISH_ATTEMPTS:
        # The model sometimes stops without calling the tool. One firm nudge, then give up safely.
        agent("You have not published a page yet. Write the page now and call publish_page.")
    return log


def local_publisher(out_dir: Path) -> Callable[[int, str], str]:
    def publish(level: int, html: str) -> str:
        target = out_dir / f"level-{level}" / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html)
        return f"Published to {target}"
    return publish
