from __future__ import annotations

from pathlib import Path


TOURNAMENT_OPTIONS_DESKTOP = (
    "tournament:[{value:300,label:'300 / tournament'},"
    "{value:400,label:'400 / tournament'},"
    "{value:500,label:'500 / tournament'},"
    "{value:600,label:'600 / tournament'},"
    "{value:800,label:'800 / tournament'},"
    "{value:1000,label:'1000 / tournament'}]"
)

TOURNAMENT_OPTIONS_QUICK = (
    "tournament:[{value:300,label:'300 · Tournament'},"
    "{value:400,label:'400 · Tournament'},"
    "{value:500,label:'500 · Tournament'},"
    "{value:600,label:'600 · Tournament'},"
    "{value:800,label:'800 · Tournament'},"
    "{value:1000,label:'1000 · Tournament'}]"
)


def apply(root: Path) -> None:
    _server(root / "server.py")
    _app(root / "static" / "app.js")
    _index(root / "static" / "index.html")
    _sw(root / "static" / "sw.js")


def _server(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    old = 'tournament_initials = {400: "400 / tournament", 1000: "1000 / tournament"}'
    new = (
        'tournament_initials = {'
        '300: "300 / tournament", '
        '400: "400 / tournament", '
        '500: "500 / tournament", '
        '600: "600 / tournament", '
        '800: "800 / tournament", '
        '1000: "1000 / tournament"'
        '}'
    )
    if old in text:
        text = text.replace(old, new, 1)
    elif new not in text:
        raise RuntimeError("v1.19.1 tournament server options marker missing")

    text = text.replace('version="1.19.0"', 'version="1.19.1"')
    text = text.replace('"version":"1.19.0"', '"version":"1.19.1"')
    text = text.replace('request.url.query == "v=38"', 'request.url.query == "v=40"')
    path.write_text(text, encoding="utf-8")


def _app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    old_desktop = (
        "tournament:[{value:400,label:'400 / tournament'},"
        "{value:1000,label:'1000 / tournament'}]"
    )
    if old_desktop in text:
        text = text.replace(old_desktop, TOURNAMENT_OPTIONS_DESKTOP, 1)
    elif TOURNAMENT_OPTIONS_DESKTOP not in text:
        raise RuntimeError("v1.19.1 desktop tournament options marker missing")

    old_quick = (
        "tournament:[{value:400,label:'400 · Tournament'},"
        "{value:1000,label:'1000 · Tournament'}]"
    )
    if old_quick in text:
        text = text.replace(old_quick, TOURNAMENT_OPTIONS_QUICK, 1)
    elif TOURNAMENT_OPTIONS_QUICK not in text:
        raise RuntimeError("v1.19.1 quick tournament options marker missing")

    path.write_text(text, encoding="utf-8")


def _index(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace('?v=38', '?v=40')
    path.write_text(text, encoding="utf-8")


def _sw(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace('jj-arena-live-v38', 'jj-arena-live-v40')
    path.write_text(text, encoding="utf-8")
