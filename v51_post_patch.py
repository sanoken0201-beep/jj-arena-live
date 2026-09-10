from __future__ import annotations

from pathlib import Path


def apply(root: Path) -> None:
    path = root / "static" / "app.js"
    text = path.read_text(encoding="utf-8")
    marker = "v1.23.0 sound storage fallback"
    if marker not in text:
        old_init = "let jjV123SoundEnabled=localStorage.getItem(JJ_V123_SOUND_KEY)!=='0';"
        new_init = """// v1.23.0 sound storage fallback: isolated tests/private contexts may not expose localStorage.\n  function jjV123StoredSound(){try{return typeof localStorage==='undefined'||localStorage.getItem(JJ_V123_SOUND_KEY)!=='0'}catch{return true}}\n  let jjV123SoundEnabled=jjV123StoredSound();"""
        if old_init not in text:
            raise RuntimeError("v1.23 sound preference initializer missing")
        text = text.replace(old_init, new_init, 1)

        old_set = "localStorage.setItem(JJ_V123_SOUND_KEY,jjV123SoundEnabled?'1':'0');"
        new_set = "try{if(typeof localStorage!=='undefined')localStorage.setItem(JJ_V123_SOUND_KEY,jjV123SoundEnabled?'1':'0')}catch{}"
        if old_set not in text:
            raise RuntimeError("v1.23 sound preference setter missing")
        text = text.replace(old_set, new_set, 1)

    # Poker-only render helpers are absent in isolated page/unit contexts. The
    # v1.23 enhancements must therefore decorate them only when that surface is
    # actually present instead of making unrelated pages fail during JS load.
    guards = (
        (
            "const jjV123BaseRenderSeat=renderSeat;\n  renderSeat=function(seat){",
            "const jjV123BaseRenderSeat=typeof renderSeat==='function'?renderSeat:null;\n  if(jjV123BaseRenderSeat)renderSeat=function(seat){",
        ),
        (
            "const jjV123BaseRenderActionBar=renderActionBar;\n  renderActionBar=function(){",
            "const jjV123BaseRenderActionBar=typeof renderActionBar==='function'?renderActionBar:null;\n  if(jjV123BaseRenderActionBar)renderActionBar=function(){",
        ),
        (
            "const jjV123BaseRenderPokerRoom=renderPokerRoom;\n  renderPokerRoom=function(){",
            "const jjV123BaseRenderPokerRoom=typeof renderPokerRoom==='function'?renderPokerRoom:null;\n  if(jjV123BaseRenderPokerRoom)renderPokerRoom=function(){",
        ),
    )
    for old, new in guards:
        if new in text:
            continue
        if old not in text:
            raise RuntimeError(f"v1.23 render guard target missing: {old.splitlines()[0]}")
        text = text.replace(old, new, 1)

    # The periodic status helper is useful only when the table UI exists. This
    # also keeps isolated VM tests and non-table routes free of poker-only work.
    old_timer = "window.setInterval(()=>{jjV123ClockFeedback();jjV123ActionState()},500);"
    new_timer = "if(typeof window!=='undefined'&&typeof renderPokerRoom==='function')window.setInterval(()=>{jjV123ClockFeedback();jjV123ActionState()},500);"
    if new_timer not in text:
        if old_timer not in text:
            raise RuntimeError("v1.23 status timer target missing")
        text = text.replace(old_timer, new_timer, 1)

    path.write_text(text, encoding="utf-8")
