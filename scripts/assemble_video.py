"""Assemble the demo video: slides + phone clips + Polly narration -> out/video/brownout-demo.mp4"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V = ROOT / "out" / "video"
PAD = 1.0  # seconds of silence after each narration line

# scene -> phone clip shown on the left of the slide (None = full-screen slide)
SCENES = [("s1", "full.webm"), ("s2", "throttled.webm"), ("s3", None), ("s4", None),
          ("s5", None), ("s6", "live.webm"), ("s7", None), ("s8", None)]


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def scene(name: str, clip: str | None) -> Path:
    audio = V / "audio" / f"{name}.mp3"
    d = duration(audio) + PAD
    out = V / "parts" / f"{name}.mp4"
    out.parent.mkdir(exist_ok=True)
    slide = V / "slides" / f"{name}.png"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-t", f"{d}", "-i", str(slide)]
    if clip:
        src = V / clip
        speed = max(1.0, duration(src) / d)
        cmd += ["-i", str(src), "-i", str(audio), "-filter_complex",
                f"[1:v]crop=iw/2:ih/2:0:0,setpts=PTS/{speed},scale=-2:960:flags=lanczos,format=yuv420p[ph];"
                f"[0:v][ph]overlay=x=200:y=60:shortest=0[v]",
                "-map", "[v]", "-map", "2:a"]
    else:
        cmd += ["-i", str(audio), "-map", "0:v", "-map", "1:a"]
    cmd += ["-t", f"{d}", "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100",
            "-af", f"apad=pad_dur={PAD}", str(out)]
    subprocess.run(cmd, check=True)
    return out


def main() -> None:
    parts = [scene(n, c) for n, c in SCENES]
    lst = V / "parts" / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    final = V / "brownout-demo.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(final)], check=True)
    print(final, f"{duration(final):.1f}s")


if __name__ == "__main__":
    main()
