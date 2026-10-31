"""Evaluate Brownout against two alternatives on every hazard x alert level.

  baseline   - mechanically strip the heavy site (no judgement)
  unguarded  - the same agent, but publish_page has no deterministic guard
  brownout   - the agent with PublishGuard (budget + required facts)

Writes out/eval/results.json and prints a summary table.
Run:  uv run python scripts/evaluate.py --trials 3
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from brownout.agent import brownout, local_publisher
from brownout.baseline import baseline_page
from brownout.facts import HAZARDS, LEVELS, check

OUT = Path("out/eval")


def row(variant: str, hazard: str, level: int, html: str | None, attempts: int, seconds: float) -> dict:
    if html is None:
        return {"variant": variant, "hazard": hazard, "level": level, "published": False,
                "passed": False, "attempts": attempts, "seconds": round(seconds, 1)}
    c = check(html, hazard, level)
    return {"variant": variant, "hazard": hazard, "level": level, "published": True, "passed": c.passed,
            "bytes_gzip": c.size, "budget": c.budget, "retention": round(c.retention, 3),
            "missing": c.missing, "forbidden": c.forbidden, "attempts": attempts, "seconds": round(seconds, 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=3)
    args = ap.parse_args()
    rows = []
    for hazard in HAZARDS:
        for level in LEVELS:
            rows.append(row("baseline", hazard, level, baseline_page(hazard, level), 0, 0))
            for variant, guard in [("unguarded", False), ("brownout", True)]:
                for t in range(args.trials):
                    start = time.time()
                    log = brownout(hazard, level, local_publisher(OUT / variant / hazard / f"t{t}"), guard=guard)
                    rows.append(row(variant, hazard, level, log.published, log.attempts, time.time() - start))
                    print(json.dumps(rows[-1]))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(rows, indent=2))
    summarize(rows)


def summarize(rows: list[dict]) -> None:
    print(f"\n{'variant':<10} {'runs':>5} {'pass':>6} {'retention':>10} {'forbidden':>10} {'avg bytes':>10} {'avg tries':>10}")
    for v in ["baseline", "unguarded", "brownout"]:
        rs = [r for r in rows if r["variant"] == v]
        pub = [r for r in rs if r["published"]]
        pass_rate = sum(r["passed"] for r in rs) / len(rs)
        ret = sum(r["retention"] for r in pub) / len(pub) if pub else 0
        forb = sum(bool(r["forbidden"]) for r in pub)
        size = sum(r["bytes_gzip"] for r in pub) / len(pub) if pub else 0
        tries = sum(r["attempts"] for r in rs) / len(rs)
        print(f"{v:<10} {len(rs):>5} {pass_rate:>6.0%} {ret:>10.0%} {forb:>10} {size:>10,.0f} {tries:>10.1f}")


if __name__ == "__main__":
    main()
