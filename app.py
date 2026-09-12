"""Production entrypoint for JJ Arena Live after the v2 core materialization cutover.

Render continues to start ``app:app``. This shim delegates to the committed,
verified materialized v1.24.4 implementation so production no longer rebuilds
the historical patch chain on every process start.

The former reconstructed startup path remains in ``app_legacy.py`` as the
parity oracle and rollback reference.
"""
from __future__ import annotations

from pathlib import Path


_ROOT = Path(__file__).resolve().parent
_MATERIALIZED_STATIC = _ROOT / "materialized_v1244" / "static"
_TODAYS_JJ_MARKER = "v2 today's-jj contrast hardening 2026-09-12"
_TODAYS_JJ_CSS = r'''

/* v2 today's-jj contrast hardening 2026-09-12
   These rules intentionally target the cards themselves, not only their parent
   learning shell. The home layout has changed several times and the text must
   remain readable even if a card is moved to another container. */
.jj-study-card,
.jj-video-card{
  color:#f4f8f6!important;
  -webkit-text-fill-color:currentColor;
}
.jj-study-card:link,
.jj-study-card:visited,
.jj-video-card:link,
.jj-video-card:visited{
  color:#f4f8f6!important;
  -webkit-text-fill-color:#f4f8f6!important;
}
.jj-study-card h3,
.jj-video-card h3{
  color:#ffffff!important;
  -webkit-text-fill-color:#ffffff!important;
  opacity:1!important;
  text-shadow:0 1px 2px rgba(0,0,0,.32)!important;
}
.jj-study-card p,
.jj-video-card p{
  color:#d7e2dc!important;
  -webkit-text-fill-color:#d7e2dc!important;
  opacity:1!important;
}
.jj-study-meta,
.jj-study-meta>span:not(.jj-study-source){
  color:#c4d0ca!important;
  -webkit-text-fill-color:#c4d0ca!important;
  opacity:1!important;
}
.jj-study-source,
.jj-video-kind{
  color:#a8ebcb!important;
  -webkit-text-fill-color:#a8ebcb!important;
  opacity:1!important;
}
.jj-video-kind.is-motivation{
  color:#f6dc8d!important;
  -webkit-text-fill-color:#f6dc8d!important;
}
.jj-study-card footer,
.jj-video-card footer,
.jj-study-card footer>span,
.jj-video-card footer>span{
  color:#c4d0ca!important;
  -webkit-text-fill-color:#c4d0ca!important;
  opacity:1!important;
}
.jj-study-card footer b,
.jj-video-card footer b{
  color:#ffe08a!important;
  -webkit-text-fill-color:#ffe08a!important;
  opacity:1!important;
}
@media(max-width:760px){
  .jj-study-card h3,.jj-video-card h3{
    font-size:.92rem!important;
    line-height:1.52!important;
    font-weight:800!important;
  }
  .jj-study-meta{font-size:.68rem!important}
  .jj-study-card footer,.jj-video-card footer{font-size:.7rem!important}
}
'''


def _apply_todays_jj_hotfix() -> None:
    """Make learning cards unconditionally readable and invalidate old iOS CSS.

    The production runtime is materialized and intentionally immutable in git,
    but a tiny idempotent boot-time compatibility layer is safer than reopening
    the historical patch chain. It runs before the FastAPI app mounts /static.
    """
    styles = _MATERIALIZED_STATIC / "styles.css"
    index = _MATERIALIZED_STATIC / "index.html"
    sw = _MATERIALIZED_STATIC / "sw.js"

    css = styles.read_text(encoding="utf-8")
    if _TODAYS_JJ_MARKER not in css:
        styles.write_text(css.rstrip() + _TODAYS_JJ_CSS + "\n", encoding="utf-8")

    html = index.read_text(encoding="utf-8")
    html = html.replace('/static/styles.css?v=56', '/static/styles.css?v=57')
    index.write_text(html, encoding="utf-8")

    worker = sw.read_text(encoding="utf-8")
    worker = worker.replace("const CACHE='jj-arena-live-v56';", "const CACHE='jj-arena-live-v57';")
    worker = worker.replace("'/static/styles.css?v=19'", "'/static/styles.css?v=57'")
    worker = worker.replace("'/static/app.js?v=19'", "'/static/app.js?v=56'")
    sw.write_text(worker, encoding="utf-8")


_apply_todays_jj_hotfix()

import app_materialized as _materialized
from app_materialized import app, db, runtime_poker_engine, runtime_server

__all__ = ["app", "db", "runtime_poker_engine", "runtime_server"]


def __getattr__(name: str):
    """Forward legacy module-level attributes to the canonical implementation.

    The old production ``app.py`` exposed imported extension modules and
    ``DEST`` as incidental module attributes. Keeping read-only forwarding here
    avoids breaking diagnostics/tests that inspect those attributes while the
    stable ASGI surface remains the explicit exports above.
    """
    return getattr(_materialized, name)
