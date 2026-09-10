from __future__ import annotations

from pathlib import Path


def apply(root: Path) -> None:
    path = root / "static" / "app.js"
    text = path.read_text(encoding="utf-8")
    old = """  const jjV121OldRenderHome=renderHome;\n  renderHome=async function(){const r=await jjV121OldRenderHome();await jjV121LoadHomeHub();return r};\n  jjV121EnsureHomeHub();"""
    new = """  if(typeof renderHome==='function'){\n    const jjV121OldRenderHome=renderHome;\n    renderHome=async function(){const r=await jjV121OldRenderHome();await jjV121LoadHomeHub();return r};\n    jjV121EnsureHomeHub();\n  }"""
    if old in text:
        text = text.replace(old, new, 1)
    elif "if(typeof renderHome==='function')" not in text:
        raise RuntimeError("v1.21.0 home hook target missing")
    path.write_text(text, encoding="utf-8")
