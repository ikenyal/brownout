"""Measure how heavy a page is: the HTML plus every asset it pulls in.

Text files (html, css, js, json, svg) count as their gzip size, because that is
what travels over the wire. Binary files (images, video, fonts) count as-is.
Run:  uv run python scripts/measure.py site/full/index.html
"""

from __future__ import annotations

import gzip
import re
import sys
from pathlib import Path

TEXT = {".html", ".css", ".js", ".json", ".svg", ".txt"}
REF = re.compile(r"""(?:src|href)=["']([^"'#?]+)|url\(["']?([^"')]+)|fetch\(['"]([^'"]+)""")


def transfer_size(path: Path) -> int:
    data = path.read_bytes()
    return len(gzip.compress(data, 9)) if path.suffix in TEXT else len(data)


def collect(page: Path) -> dict[Path, int]:
    seen: dict[Path, int] = {}
    queue = [page]
    while queue:
        p = queue.pop()
        if p in seen or not p.exists():
            continue
        seen[p] = transfer_size(p)
        if p.suffix in {".html", ".css", ".js"}:
            for m in REF.finditer(p.read_text(errors="ignore")):
                ref = next(g for g in m.groups() if g)
                if ref.startswith(("http:", "https:", "data:", "mailto:")):
                    continue
                base = page.parent if p.suffix != ".css" else p.parent
                queue.append((base / ref).resolve())
    return seen


if __name__ == "__main__":
    page = Path(sys.argv[1]).resolve()
    files = collect(page)
    for p, n in sorted(files.items(), key=lambda kv: -kv[1]):
        print(f"{n:>12,}  {p.relative_to(page.parent)}")
    print(f"{sum(files.values()):>12,}  TOTAL ({len(files)} files)")
