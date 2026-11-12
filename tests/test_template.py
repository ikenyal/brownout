"""The template page must pass the same deterministic checks as the agent's page, for every case.

Run: uv run python tests/test_template.py   (no AWS access needed)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from brownout.facts import HAZARDS, LEVELS, check, describe
from brownout.template import template_page

for hazard in HAZARDS:
    for level in LEVELS:
        result = check(template_page(hazard, level), hazard, level)
        assert result.passed, f"{hazard} {level}: {describe(result)}"
        print(f"{hazard} level {level}: ok, {result.size} bytes gzipped (budget {result.budget})")
print("all template pages pass")
