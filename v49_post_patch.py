from __future__ import annotations

from pathlib import Path


def apply(root: Path) -> None:
    path = root / "static" / "app.js"
    text = path.read_text(encoding="utf-8")

    old_home = """  const jjV121OldRenderHome=renderHome;\n  renderHome=async function(){const r=await jjV121OldRenderHome();await jjV121LoadHomeHub();return r};\n  jjV121EnsureHomeHub();"""
    new_home = """  if(typeof renderHome==='function'){\n    const jjV121OldRenderHome=renderHome;\n    renderHome=async function(){const r=await jjV121OldRenderHome();await jjV121LoadHomeHub();return r};\n    jjV121EnsureHomeHub();\n  }"""
    if old_home in text:
        text = text.replace(old_home, new_home, 1)
    elif "if(typeof renderHome==='function')" not in text:
        raise RuntimeError("v1.21.0 home hook target missing")

    old_listener = """  document.addEventListener('click',e=>{\n    const go=e.target.closest('[data-jj-go]');if(go)switchView(go.dataset.jjGo);\n    const hand=e.target.closest('[data-jj-hand]');if(hand){switchView('analysis');setTimeout(()=>jjOpenHand?.(hand.dataset.jjHand).catch(err=>toast(err.message)),100)}\n  });"""
    new_listener = """  function jjV121HomeClick(e){\n    const go=e.target.closest('[data-jj-go]');if(go)switchView(go.dataset.jjGo);\n    const hand=e.target.closest('[data-jj-hand]');if(hand){switchView('analysis');setTimeout(()=>jjOpenHand?.(hand.dataset.jjHand).catch(err=>toast(err.message)),100)}\n  }"""
    if old_listener in text:
        text = text.replace(old_listener, new_listener, 1)
    elif "function jjV121HomeClick(e)" not in text:
        raise RuntimeError("v1.21.0 global home click target missing")

    old_refresh = """    $('#jjHomeHubRefresh')?.addEventListener('click',jjV121LoadHomeHub);"""
    new_refresh = """    $('#jjHomeHubRefresh')?.addEventListener('click',jjV121LoadHomeHub);\n    hub.addEventListener('click',jjV121HomeClick);"""
    if old_refresh in text:
        text = text.replace(old_refresh, new_refresh, 1)
    elif "hub.addEventListener('click',jjV121HomeClick)" not in text:
        raise RuntimeError("v1.21.0 home hub listener target missing")

    path.write_text(text, encoding="utf-8")
