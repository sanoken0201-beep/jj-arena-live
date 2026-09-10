from __future__ import annotations

from pathlib import Path


def apply(root: Path) -> None:
    _poker(root / "poker_engine.py")


def _poker(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = '# v1.20.0 completed-hand card privacy'
    if marker in text:
        return

    old_head = '''def public_state(state: dict[str, Any], viewer_id: int | None = None) -> dict[str, Any]:
    out = {k: v for k, v in state.items() if k not in ("seats", "hand")}; reveal_all = bool(state.get("hand") and state["hand"].get("phase") == "complete"); out["seats"] = []
'''
    new_head = '''def public_state(state: dict[str, Any], viewer_id: int | None = None) -> dict[str, Any]:
    # v1.20.0 completed-hand card privacy
    # A completed hand does not make every folded hand public. Only the viewer's
    # own cards and players who actually reached showdown are disclosed.
    out = {k: v for k, v in state.items() if k not in ("seats", "hand")}
    showdown_scores = ((state.get("hand") or {}).get("showdown") or {}).get("scores") or {}
    showdown_ids = {int(uid) for uid in showdown_scores.keys()}
    out["seats"] = []
'''
    if old_head not in text:
        raise RuntimeError('v1.20.0 public_state header target missing')
    text = text.replace(old_head, new_head, 1)

    old_condition = '''        if p["user_id"] == viewer_id or reveal_all: item["cards"] = list(p.get("cards", []))
        elif p.get("in_hand"): item["cards"] = ["??", "??"]
        else: item["cards"] = []
'''
    new_condition = '''        if p["user_id"] == viewer_id or int(p["user_id"]) in showdown_ids:
            item["cards"] = list(p.get("cards", []))
        elif p.get("in_hand"):
            item["cards"] = ["??", "??"]
        else:
            item["cards"] = []
'''
    if old_condition not in text:
        raise RuntimeError('v1.20.0 public_state reveal target missing')
    text = text.replace(old_condition, new_condition, 1)
    path.write_text(text, encoding="utf-8")
