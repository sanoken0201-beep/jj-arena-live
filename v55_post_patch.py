from __future__ import annotations

from pathlib import Path


def apply(root: Path) -> None:
    # This branch is intentionally stacked on the non-poker PR while a separate
    # Work stream is changing online poker. Keep the parent's release/cache IDs
    # so final integration can assign one authoritative version after rebasing.
    server = root / "server.py"
    text = server.read_text(encoding="utf-8")
    text = text.replace('version="1.24.4"', 'version="1.24.3"')
    text = text.replace('"version":"1.24.4"', '"version":"1.24.3"')
    text = text.replace('request.url.query == "v=56"', 'request.url.query == "v=55"')
    server.write_text(text, encoding="utf-8")

    index = root / "static" / "index.html"
    index.write_text(index.read_text(encoding="utf-8").replace("?v=56", "?v=55"), encoding="utf-8")

    sw = root / "static" / "sw.js"
    sw.write_text(sw.read_text(encoding="utf-8").replace("jj-arena-live-v56", "jj-arena-live-v55"), encoding="utf-8")
