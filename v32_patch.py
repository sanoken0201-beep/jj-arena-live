from __future__ import annotations
from pathlib import Path
import re


def apply(root: Path) -> None:
    _server(root / 'server.py')
    _index(root / 'static' / 'index.html')
    _sw(root / 'static' / 'sw.js')


def _server(p: Path) -> None:
    s = p.read_text(encoding='utf-8')

    # v1.14 introduced an endpoint function named `table_presence`, but an
    # earlier production-presence layer already owns a dict with that exact
    # global name. Python then replaced the dict with the function object and
    # every GET /api/tables/{id} failed inside touch_presence() with:
    # TypeError: 'function' object does not support item assignment.
    # Keep the route URL unchanged; only the Python function name must differ.
    old = 'async def table_presence(table_id: str, payload: TablePresenceIn, user=Depends(current_user)):'
    new = 'async def update_table_presence(table_id: str, payload: TablePresenceIn, user=Depends(current_user)):'
    count = s.count(old)
    if count != 1:
        raise RuntimeError(f'v1.16.3 presence endpoint name target mismatch: {count}')
    s = s.replace(old, new, 1)

    s = s.replace('version="1.16.2"', 'version="1.16.3"').replace('"version":"1.16.2"', '"version":"1.16.3"')
    s = s.replace('request.url.query == "v=31"', 'request.url.query == "v=32"')
    p.write_text(s, encoding='utf-8')


def _index(p: Path) -> None:
    s = p.read_text(encoding='utf-8').replace('?v=31', '?v=32')
    p.write_text(s, encoding='utf-8')


def _sw(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    s = re.sub(r'jj-arena-live-v\d+', 'jj-arena-live-v32', s)
    p.write_text(s, encoding='utf-8')
