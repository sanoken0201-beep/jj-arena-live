from __future__ import annotations

from pathlib import Path


def apply(root: Path) -> None:
    _poker(root / "poker_engine.py")


def _poker(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "# v1.20.0 completed-hand card privacy"
    if marker in text:
        return

    # Append a final wrapper rather than rewriting an older implementation of
    # public_state. Earlier release patches may wrap/replace that function, so a
    # final sanitizing layer is safer and keeps every other public-state field
    # exactly as the verified runtime produced it.
    addon = r'''

# v1.20.0 completed-hand card privacy
# Never reveal a mucked/folded opponent hand just because the hand reached the
# complete state. The viewer always sees their own cards; other players' cards
# are disclosed only when that player actually reached showdown.
_jj_v120_public_state_before_privacy = public_state


def public_state(state: dict[str, Any], viewer_id: int | None = None) -> dict[str, Any]:
    out = _jj_v120_public_state_before_privacy(state, viewer_id)
    hand = state.get("hand") or {}
    scores = ((hand.get("showdown") or {}).get("scores") or {})
    showdown_ids: set[int] = set()
    for raw_uid in scores.keys():
        try:
            showdown_ids.add(int(raw_uid))
        except (TypeError, ValueError):
            continue

    private_by_uid = {}
    for player in state.get("seats", []):
        try:
            uid = int(player.get("user_id"))
        except (TypeError, ValueError):
            continue
        private_by_uid[uid] = player

    for item in out.get("seats", []):
        try:
            uid = int(item.get("user_id"))
        except (TypeError, ValueError):
            item["cards"] = []
            continue
        private = private_by_uid.get(uid) or {}
        if viewer_id is not None and uid == int(viewer_id):
            item["cards"] = list(private.get("cards") or [])
        elif uid in showdown_ids:
            item["cards"] = list(private.get("cards") or [])
        elif bool(private.get("in_hand")):
            item["cards"] = ["??", "??"] if private.get("cards") else []
        else:
            item["cards"] = []
    return out
'''
    path.write_text(text.rstrip() + addon + "\n", encoding="utf-8")
