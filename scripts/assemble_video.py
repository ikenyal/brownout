"""Assemble the demo video -> out/video/brownout-demo.mp4

Same house style as the earlier Builder Center videos: Amazon Polly (Brian, generative),
burned-in captions one sentence at a time, short fades, © overlay on the title and end cards.
Phone clips (Playwright recordings) sit on the left of their slide.
Run:  AWS_PROFILE=... uv run python scripts/assemble_video.py
"""

from __future__ import annotations

import html
import json
import re
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
V = ROOT / "out" / "video"
PARTS = V / "parts"
VOICE, LEAD, TAIL = "Brian", 0.4, 0.8
NARRATION = json.loads((ROOT / "docs" / "narration.json").read_text())
SCENES = [("s1", "full.webm"), ("s2", "throttled.webm"), ("s3", None), ("s4", None),
          ("s5", None), ("s6", "live.webm"), ("s7", None), ("s8", None)]
BAND_CSS = """body{margin:0;width:1920px;height:200px;background:#0b130e;display:flex;align-items:center;justify-content:center}
.cap{font-family:-apple-system,'Helvetica Neue',sans-serif;font-size:40px;line-height:1.3;font-weight:600;color:#f3f6f3;
text-align:center;padding:0 120px}"""


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def duration(path: Path) -> float:
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]))


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def bands(page, sid: str, sents: list[str]) -> list[Path]:
    out = []
    for i, s in enumerate(sents):
        page.set_content(f"<html><head><meta charset='utf-8'><style>{BAND_CSS}</style></head>"
                         f"<body><div class='cap'>{html.escape(s)}</div></body></html>")
        png = PARTS / f"{sid}-cap{i}.png"
        page.screenshot(path=str(png))
        out.append(png)
    return out


def scene(page, sid: str, clip: str | None) -> Path:
    text = NARRATION[int(sid[1:]) - 1]
    audio = PARTS / f"{sid}.mp3"
    run(["aws", "polly", "synthesize-speech", "--engine", "generative", "--voice-id", VOICE,
         "--output-format", "mp3", "--sample-rate", "24000", "--text", text, str(audio)])
    a = duration(audio)
    total = LEAD + a + TAIL
    sents = sentences(text)
    caps = bands(page, sid, sents)
    chars = [len(s) for s in sents]
    starts, t = [], LEAD
    for c in chars:
        starts.append(t)
        t += a * c / sum(chars)
    ends = starts[1:] + [total]
    starts[0] = 0.0

    cmd = ["ffmpeg", "-y", "-v", "error", "-loop", "1", "-t", f"{total:.3f}", "-i", str(V / "slides" / f"{sid}.png")]
    filters, last, idx = [], "0:v", 1
    if clip:
        src = V / clip
        speed = max(1.0, duration(src) / total)
        cmd += ["-i", str(src)]
        filters.append(f"[{idx}:v]crop=iw/2:ih/2:0:0,setpts=PTS/{speed},scale=-2:820:flags=lanczos[ph]")
        filters.append(f"[{last}][ph]overlay=x=200:y=30:eof_action=repeat[b0]")
        last, idx = "b0", idx + 1
    for i, png in enumerate(caps):
        cmd += ["-i", str(png)]
        filters.append(f"[{last}][{idx}:v]overlay=x=0:y=880:enable='between(t,{starts[i]:.3f},{ends[i]:.3f})'[c{i}]")
        last, idx = f"c{i}", idx + 1
    cmd += ["-i", str(audio)]
    filters.append(f"[{idx}:a]adelay={int(LEAD * 1000)}:all=1,apad=whole_dur={total:.3f}[a]")
    filters.append(f"[{last}]fps=30,format=yuv420p[v]")
    out = PARTS / f"{sid}.mp4"
    cmd += ["-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
            "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-ar", "48000", "-b:a", "160k", str(out)]
    run(cmd)
    print(f"{sid} narration {a:5.1f}s scene {total:5.1f}s captions {len(sents)}")
    return out


def main() -> None:
    PARTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 200})
        parts = [scene(page, sid, clip) for sid, clip in SCENES]
        browser.close()
    lst = PARTS / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    joined = PARTS / "joined.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])
    d = duration(joined)
    final = V / "brownout-demo.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(joined),
         "-vf", f"fade=t=in:st=0:d=0.5,fade=t=out:st={d - 0.6:.2f}:d=0.6",
         "-af", f"afade=t=in:st=0:d=0.3,afade=t=out:st={d - 0.6:.2f}:d=0.6",
         "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-b:a", "160k", "-map_metadata", "-1", str(final)])
    print(final, f"{duration(final):.1f}s")


if __name__ == "__main__":
    main()
