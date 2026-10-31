"""Render 1920x1080 slides and backgrounds for the demo video (HTML -> PNG via Playwright)."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "video" / "slides"
CSS = """
body{margin:0;width:1920px;height:1080px;background:#0f1a14;color:#eef3ee;font-family:-apple-system,'Helvetica Neue',sans-serif;overflow:hidden}
.side{position:absolute;left:640px;top:0;right:100px;height:880px;display:flex;flex-direction:column;justify-content:center}
.full{position:absolute;left:0;top:0;width:1920px;height:880px;box-sizing:border-box;padding:60px 120px;display:flex;flex-direction:column;justify-content:center}
h1{font-size:84px;margin:0 0 24px;letter-spacing:-1px} h2{font-size:58px;margin:0 0 28px}
p{font-size:36px;line-height:1.45;color:#c9d6cb;margin:0 0 18px} .big{font-size:120px;font-weight:800;color:#ff6b57}
.tag{display:inline-block;align-self:flex-start;background:#ff6b57;color:#111;font-weight:700;font-size:28px;padding:6px 16px;border-radius:8px;margin-bottom:24px}
table{border-collapse:collapse;font-size:34px;margin-top:10px} td,th{padding:14px 26px;border-bottom:1px solid #2c4034;text-align:left} th{color:#9fb6a5;font-weight:600}
.ok{color:#7ee08a;font-weight:700} .bad{color:#ff6b57;font-weight:700}
pre{font-size:27px;line-height:1.5;background:#08110c;padding:30px 36px;border-radius:14px;color:#d8e6da;margin:0}
.flow{display:flex;align-items:center;gap:18px;flex-wrap:wrap;font-size:30px}
.box{background:#1d2e23;border:2px solid #3d5c48;border-radius:14px;padding:18px 22px} .hl{border-color:#ff6b57}
.arrow{font-size:40px;color:#7d9886} small{font-size:26px;color:#8aa293} .copy{position:absolute;right:60px;top:820px;font-size:24px;color:#6b7f72}
"""


def side(tag: str, title: str, body: str) -> str:
    return f'<div class="side"><div><span class="tag">{tag}</span></div><h2>{title}</h2>{body}</div>'


SLIDES = {
    "s1": side("Example City (fictional)", "A website built for good days",
               '<div class="big">28 MB</div><p>Video background, photo carousel, big map, web font.</p>'),
    "s2": side("Congested 3G · 400 kbit/s", "Still loading after 3 minutes",
               "<p>The shelter list is at the very bottom, under the video.</p>"),
    "s3": '<div class="full"><span class="tag">Strands Agents SDK · Amazon Bedrock AgentCore</span>'
          '<h1 style="font-size:150px">Brownout</h1><p style="font-size:46px">As a disaster gets worse,<br>the city website gets lighter, not slower.</p>'
          '<p><small>AWS Builder Center Hackathon: Strands SDK: Workshop to Ship · Climate resilience</small></p></div>'
          '<div class="copy">© 2026 Kento Ikeda (@ikenyal)</div>',
    "s4": '<div class="full"><h2>How it works</h2><div class="flow">'
          '<div class="box">EventBridge<br><small>AlertLevelChanged</small></div><span class="arrow">→</span>'
          '<div class="box">Lambda<br><small>thin adapter</small></div><span class="arrow">→</span>'
          '<div class="box hl">AgentCore Runtime<br><small>Writer agent</small></div><span class="arrow">⇄</span>'
          '<div class="box">Curator agent<br><small>what must stay</small></div></div>'
          '<div class="flow" style="margin-top:40px"><div class="box hl">PublishGuard hook<br><small>code checks + Verifier agent</small></div>'
          '<span class="arrow">→</span><div class="box">S3<br><small>checked page only</small></div><span class="arrow">→</span>'
          '<div class="box">CloudFront KeyValueStore<br><small>level = 4</small></div><span class="arrow">→</span>'
          '<div class="box">CloudFront Function<br><small>routes every URL</small></div></div>'
          '<p style="margin-top:44px">Facts come only from the city\'s data file. The agent decides what to keep and how to say it.</p></div>',
    "s5": '<div class="full"><h2>The rules that matter are code, not prompt</h2><pre>'
          'class PublishGuard(HookProvider):\n'
          '    def guard(self, event: BeforeToolCallEvent):\n'
          '        if event.tool_use["name"] != "publish_page": return\n'
          '        result = check(html, hazard, level)   # size, required facts, unsafe shelters, invented numbers\n'
          '        if result.passed:\n'
          '            result.unsupported = unsupported_sentences(verifier, html)   # Verifier agent\n'
          '        if not result.passed:\n'
          '            event.cancel_tool = f"Refused, page not published. {describe(result)}"</pre>'
          '<p style="margin-top:30px"><span class="bad">Refused:</span> Remove shelter:S3 (\'Riverside Community Hall\'):'
          ' it is NOT safe for this hazard.</p><p><span class="bad">Refused:</span> Not supported by the city data:'
          ' "Drop, take cover under a sturdy piece of furniture, and hold on."</p></div>',
    "s6": side("Live on AWS · sped up", "One key write switches the site",
               "<p>Full site → Level 4 → Level 5 → full site.</p><p>No deployment. No cache invalidation.</p>"
               "<p><small>Measured: 27 to 47 s from event to the live page. Agent: about 7 to 8 s.</small></p>"),
    "s7": '<div class="full" style="padding-top:30px"><h2>Light is not enough. It has to be right.</h2><table>'
          '<tr><th>6 scenarios, 3 runs each</th><th>Pass</th><th>Facts kept</th><th>Unsafe shelter</th><th>Unsupported</th></tr>'
          '<tr><td>Strip media</td><td class="bad">0 of 6</td><td>75%</td><td class="bad">3 of 6</td><td class="bad">6 of 6</td></tr>'
          '<tr><td>Agent, no guard</td><td>13 of 18</td><td>96%</td><td>0 of 18</td><td class="bad">5 of 18</td></tr>'
          '<tr><td>Brownout</td><td class="ok">18 of 18</td><td class="ok">100%</td><td class="ok">0 of 18</td><td class="ok">0 of 18</td></tr></table>'
          '<p style="margin-top:36px">Every Brownout page: under 1 KB. Fully loaded in 0.5 s on congested 3G, 1.0 s on 2G.'
          ' The full site: not loaded after 180 s.</p></div>',
    "s8": '<div class="full"><h1 style="font-size:130px">Brownout</h1><p style="font-size:46px">Lighter when it matters most.</p>'
          '<p style="margin-top:50px">github.com/ikenyal/brownout</p><p><small>Example City is fictional. Built with Strands Agents SDK,'
          ' Amazon Bedrock AgentCore, Amazon Nova, Amazon CloudFront. Narration voiced by Amazon Polly.</small></p></div>'
          '<div class="copy">© 2026 Kento Ikeda (@ikenyal)</div>',
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        for name, body in SLIDES.items():
            page.set_content(f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>")
            page.screenshot(path=str(OUT / f"{name}.png"))
        browser.close()
    print("saved", OUT)


if __name__ == "__main__":
    main()
