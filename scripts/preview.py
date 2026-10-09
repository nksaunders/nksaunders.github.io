#!/usr/bin/env python
"""Preview the site locally without installing Ruby or Jekyll.

    pip install python-liquid pyyaml
    python scripts/preview.py

Then open http://localhost:8000. Re-run after editing to see changes.

Why this is needed: the pages are Jekyll templates ({% for %} loops that pull
from _data/*.yml, shared pieces from _includes/), and they link CSS, images
and fonts from the site root (/assets/...). Double-clicking an .html file shows
the raw template with no styles. GitHub Pages fills the templates in when it
publishes; this script does the same thing locally and serves the result.
"""
import datetime
import http.server
import re
import shutil
import socketserver
import sys
from functools import partial
from pathlib import Path

import yaml
from liquid import Environment

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_preview"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
SKIP = {"_preview", "_site", "_data", "_includes", ".git", "spotlight", "scripts", "films"}
INCLUDE = re.compile(r"{%-?\s*include\s+([\w./-]+)\s*-?%}")

config = yaml.safe_load((ROOT / "_config.yml").read_text())
config["time"] = datetime.datetime.now()
config["data"] = {p.stem: yaml.safe_load(p.read_text()) for p in (ROOT / "_data").glob("*.yml")}


def expand_includes(text):
    # Jekyll-style {% include file.html %} (unquoted), resolved from _includes/.
    for _ in range(5):
        text = INCLUDE.sub(lambda m: (ROOT / "_includes" / m.group(1)).read_text(), text)
    return text


if OUT.exists():
    shutil.rmtree(OUT)
shutil.copytree(ROOT, OUT, ignore=lambda d, names: [n for n in names if n in SKIP or n.startswith(".")])

env = Environment()
for page in OUT.rglob("*.html"):
    text = page.read_text()
    if text.startswith("---"):
        body = re.sub(r"^---\n.*?---\n", "", text, count=1, flags=re.S)
        page.write_text(env.from_string(expand_includes(body)).render(site=config))

class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")  # always serve the latest build
        super().end_headers()


handler = partial(NoCacheHandler, directory=str(OUT))
socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("127.0.0.1", PORT), handler) as httpd:
    print(f"Preview at http://localhost:{PORT}  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
