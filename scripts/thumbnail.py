"""YouTube thumbnail (1280x720) -> ~/Downloads/brownout-thumbnail.png"""
from pathlib import Path
from playwright.sync_api import sync_playwright

HTML = """<html><head><meta charset='utf-8'><style>
body{margin:0;width:1280px;height:720px;background:#0f1a14;color:#eef3ee;font-family:-apple-system,'Helvetica Neue',sans-serif;
position:relative;overflow:hidden}
.t{position:absolute;left:80px;top:90px;font-size:150px;font-weight:800;letter-spacing:-3px}
.s{position:absolute;left:84px;top:290px;font-size:40px;color:#c9d6cb}
.n{position:absolute;left:84px;top:390px;font-size:96px;font-weight:800}
.n .a{color:#ff6b57} .n .b{color:#7ee08a} .n .x{color:#7d9886;font-weight:400}
.h{position:absolute;left:84px;top:590px;font-size:30px;font-weight:600;color:#eef3ee}
.k{position:absolute;left:84px;top:636px;font-size:24px;color:#8aa293}
</style></head><body>
<div class='t'>Brownout</div>
<div class='s'>A city website that gets lighter as a disaster gets worse</div>
<div class='n'><span class='a'>28 MB</span> <span class='x'>→</span> <span class='b'>&lt; 1 KB</span></div>
<div class='h'>Strands SDK: Workshop to Ship</div>
<div class='k'>#strands-agents · Amazon Bedrock AgentCore · Climate resilience</div>
</body></html>"""

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    page = b.new_page(viewport={"width": 1280, "height": 720})
    page.set_content(HTML)
    out = Path.home() / "Downloads" / "brownout-thumbnail.png"
    page.screenshot(path=str(out))
    b.close()
print(out)
