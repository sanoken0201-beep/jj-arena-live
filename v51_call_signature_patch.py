from __future__ import annotations

from pathlib import Path


def apply(root: Path) -> None:
    _engine(root / "poker_engine.py")
    _server(root / "server.py")


def _engine(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "v1.23.0 uncontested award call-signature compatibility"
    if marker in text:
        return
    addon = r'''

# v1.23.0 uncontested award call-signature compatibility.
# The reconstructed engine's apply_action() calls _award_uncontested(state,
# winner), while v1.23's final no-flop-no-drop wrapper also calls it internally
# with state only. Keep both historical contracts valid without duplicating the
# settlement logic.
_jj_v123_one_arg_award_uncontested = _award_uncontested


def _award_uncontested(state: dict, winner: dict | None = None) -> None:
    return _jj_v123_one_arg_award_uncontested(state)
'''
    path.write_text(text.rstrip() + addon + "\n", encoding="utf-8")


def _server(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    # v1.23 serves app.js/styles.css with ?v=51. Keep the immutable-cache
    # allowlist synchronized with that public asset version instead of leaving
    # those requests on the generic one-day cache policy.
    text = text.replace('request.url.query == "v=50"', 'request.url.query == "v=51"')
    path.write_text(text, encoding="utf-8")
