"""The fallback page must pass the same deterministic checks as the agent's page, for every case.

Run: uv run python tests/test_fallback.py   (no AWS access needed)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from brownout.facts import HAZARDS, LEVELS, check, describe
from brownout.fallback import fallback_page

for hazard in HAZARDS:
    for level in LEVELS:
        result = check(fallback_page(hazard, level), hazard, level)
        assert result.passed, f"{hazard} {level}: {describe(result)}"
        print(f"{hazard} level {level}: ok, {result.size} bytes gzipped (budget {result.budget})")
print("all fallback pages pass")
