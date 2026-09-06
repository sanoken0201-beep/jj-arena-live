from __future__ import annotations
from pathlib import Path
import re


def apply(root: Path) -> None:
    _engine(root/'poker_engine.py')
    _server(root/'server.py')
    _index(root/'static'/'index.html')
    _sw(root/'static'/'sw.js')


def _engine(p: Path) -> None:
    s=p.read_text(encoding='utf-8')
    target='''    state["next_hand_at_epoch"] = None\n    try:\n        _jj_original_start_hand(state)\n'''
    repl='''    state["next_hand_at_epoch"] = None\n    # The previous result is shown only during the inter-hand pause. Clear it\n    # before the next deal so an old winner banner can never overlap a new hand.\n    state["last_result"] = None\n    try:\n        _jj_original_start_hand(state)\n'''
    if target not in s:
        raise RuntimeError('v1.14.2 start-hand result marker missing')
    s=s.replace(target,repl,1)
    p.write_text(s,encoding='utf-8')


def _server(p: Path) -> None:
    s=p.read_text(encoding='utf-8')
    s=s.replace('version="1.14.1"','version="1.14.2"').replace('"version":"1.14.1"','"version":"1.14.2"')
    s=s.replace('request.url.query == "v=25"','request.url.query == "v=26"')
    p.write_text(s,encoding='utf-8')


def _index(p: Path) -> None:
    s=p.read_text(encoding='utf-8').replace('?v=25','?v=26')
    p.write_text(s,encoding='utf-8')


def _sw(p: Path) -> None:
    s=p.read_text(encoding='utf-8')
    s=re.sub(r'jj-arena-live-v\d+','jj-arena-live-v26',s)
    p.write_text(s,encoding='utf-8')
