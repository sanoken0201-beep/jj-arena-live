from __future__ import annotations

from pathlib import Path


def apply(root: Path) -> None:
    path = root / "static" / "app.js"
    text = path.read_text(encoding="utf-8")
    marker = "v1.23.0 sound storage fallback"
    if marker in text:
        return

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
    path.write_text(text, encoding="utf-8")
