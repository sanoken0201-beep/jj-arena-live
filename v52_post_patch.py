from __future__ import annotations

from pathlib import Path


def apply(root: Path) -> None:
    path = root / "static" / "app.js"
    text = path.read_text(encoding="utf-8")
    marker = "v1.24.0 isolated-runtime media-query guard"
    if marker in text:
        return
    old = "const JJ_V124_DESKTOP_MQ=window.matchMedia('(min-width:761px)');"
    new = """// v1.24.0 isolated-runtime media-query guard.\n  const JJ_V124_DESKTOP_MQ=(typeof window!=='undefined'&&typeof window.matchMedia==='function')\n    ? window.matchMedia('(min-width:761px)')\n    : {matches:false,addEventListener:()=>{}};"""
    if old not in text:
        raise RuntimeError("v1.24 media query target missing")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
