"""Facts and checks shared by the agent, the baseline and the evaluation.

The rule of the project: the agent never invents facts. Everything it may say
comes from content/town.json, and every page is checked against
content/must_have.json before it is published.
"""

from __future__ import annotations

import gzip
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOWN = json.loads((ROOT / "content" / "town.json").read_text())
MUST = json.loads((ROOT / "content" / "must_have.json").read_text())
HAZARDS = ("flood", "earthquake")
LEVELS = (3, 4, 5)


def budget(level: int) -> int:
    return MUST["budgets_bytes_gzip"][str(level)]


def gzip_size(html: str) -> int:
    return len(gzip.compress(html.encode("utf-8"), 9))


def token(item: str) -> str:
    """The text that proves an item made it onto the page."""
    kind, key = item.split(":")
    if kind == "action":
        return f"Level {key}"
    if kind == "hotline":
        return next(h["phone"] for h in TOWN["hotlines"] if h["id"] == key)
    if kind == "shelter":
        return next(s["name"] for s in TOWN["shelters"] if s["id"] == key)
    if kind == "water":
        return next(w["name"] for w in TOWN["water_points"] if w["id"] == key)
    raise ValueError(item)


@dataclass
class Check:
    size: int
    budget: int
    required_count: int = 0
    missing: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    invented: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)

    @property
    def over_budget(self) -> bool:
        return self.size > self.budget

    @property
    def passed(self) -> bool:
        return not (self.over_budget or self.missing or self.forbidden or self.invented or self.unsupported)

    @property
    def retention(self) -> float:
        n = self.required_count
        return (n - len(self.missing)) / n if n else 1.0


def check(html: str, hazard: str, level: int) -> Check:
    rule = MUST[hazard][str(level)]
    html = re.sub(r"\s+", " ", html)  # a name split across lines is still the same name
    c = Check(size=gzip_size(html), budget=budget(level), required_count=len(rule["required"]))
    c.missing = [i for i in rule["required"] if token(i) not in html]
    c.forbidden = [i for i in rule["forbidden"] if token(i) in html]
    c.invented = invented(html)
    return c


KNOWN_PHONES = {h["phone"] for h in TOWN["hotlines"]}
KNOWN_ADDRESSES = {x["address"] for x in TOWN["shelters"] + TOWN["water_points"]}
KNOWN_PLACES = {x["name"] for x in TOWN["shelters"] + TOWN["water_points"]}
PHONE = re.compile(r"\b\d{3}-\d{4}-\d{4}\b")
ADDRESS = re.compile(r"\b\d+-\d+ [A-Z][a-z]+\b")
PLACE = re.compile(r"\b(?:[A-Z][a-z]+ ){1,3}(?:Gym|School|Hall|Center|Centre|Field|Park|Station|Hospital|Shelter)\b")


def invented(html: str) -> list[str]:
    """Phone numbers, addresses and place names that are NOT in the city data."""
    text = re.sub(r"<[^>]+>", " ", html)
    found = [f"phone '{p}'" for p in set(PHONE.findall(html)) - KNOWN_PHONES]
    found += [f"address '{a}'" for a in set(ADDRESS.findall(text)) - KNOWN_ADDRESSES]
    places = {p for p in PLACE.findall(text) if not any(p in k or k in p for k in KNOWN_PLACES)}
    found += [f"place '{p}'" for p in places]
    return sorted(found)


def describe(c: Check) -> str:
    """Feedback written for the model that has to fix the page."""
    parts = []
    if c.over_budget:
        parts.append(f"The page is {c.size:,} bytes gzipped; the limit for this level is {c.budget:,}. Cut it down.")
    for i in c.missing:
        parts.append(f"Missing required item {i}: the page must contain the exact text '{token(i)}'.")
    for i in c.forbidden:
        parts.append(f"Remove {i} ('{token(i)}'): it is NOT safe for this hazard and must not appear anywhere on the page.")
    for i in c.invented:
        parts.append(f"Remove the {i}: it is not in the city data. Never invent facts.")
    for i in c.unsupported:
        parts.append(f"Remove or rewrite this sentence, it is not supported by the city data: \"{i}\".")
    return " ".join(parts) or "OK"
