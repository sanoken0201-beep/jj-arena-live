from __future__ import annotations

import re
from pathlib import Path


def apply(root: Path) -> None:
    _server(root / "server.py")
    _index(root / "static" / "index.html")
    _sw(root / "static" / "sw.js")


def _server(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace('version="1.17.0"', 'version="1.18.0"')
    text = text.replace('"version":"1.17.0"', '"version":"1.18.0"')
    text = text.replace('request.url.query == "v=33"', 'request.url.query == "v=34"')
    path.write_text(text, encoding="utf-8")


def _index(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = '<section id="membersView" class="view admin-only">'
    if marker in text and '管理コンソールを開く' not in text:
        launch = (
            marker
            + '<div class="notice"><strong>管理機能を拡張しました。</strong> '
            + '登録アカウント、ポイント振込・回収、制度設定、監査ログは '
            + '<a href="/admin"><strong>管理コンソールを開く →</strong></a></div>'
        )
        text = text.replace(marker, launch, 1)
    text = text.replace('?v=33', '?v=34')
    path.write_text(text, encoding="utf-8")


def _sw(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'jj-arena-live-v\d+', 'jj-arena-live-v34', text)
    path.write_text(text, encoding="utf-8")
