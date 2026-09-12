from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException

import hand_history_visibility


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _Connection:
    def execute(self, sql, params):
        assert "SELECT user_id,hole_cards_json FROM jj_hand_players" in sql
        assert params == ("done",)
        return _Rows([
            {"user_id": 1, "hole_cards_json": '["As","Kd"]'},
            {"user_id": 2, "hole_cards_json": '["Qc","Jc"]'},
            {"user_id": 3, "hole_cards_json": '["7h","7s"]'},
        ])


class _DB:
    @contextmanager
    def connect(self):
        yield _Connection()


def _fake_analytics():
    def loads(value, default):
        if value is None:
            return default
        return json.loads(value)

    def detail(hand_id: str, viewer_id: int):
        if viewer_id != 1:
            raise HTTPException(404, "hand not found")
        complete = hand_id == "done"
        return {
            "hand": {"hand_id": hand_id, "completed_at": "2026-09-12T10:00:00Z" if complete else None},
            "players": [
                {"user_id": 1, "player_name": "アリス", "cards": ["As", "Kd"]},
                {"user_id": 2, "player_name": "ボブ", "cards": ["??", "??"]},
                {"user_id": 3, "player_name": "キャロル", "cards": ["??", "??"]},
            ],
            "actions": [
                {"user_id": 1, "player_name": "アリス", "action": "raise"},
                {"user_id": 2, "player_name": "ボブ", "action": "fold"},
                {"user_id": 3, "player_name": "キャロル", "action": "fold"},
            ],
        }

    def export(hand_id: str, viewer_id: int):
        detail(hand_id, viewer_id)
        return "JJ Arena Hand\n*** HOLE CARDS ***\nDealt to アリス [As Kd]\n*** SUMMARY ***\n"

    return SimpleNamespace(
        _detail_payload=detail,
        _export_text=export,
        _DB=_DB(),
        _loads=loads,
    )


def run() -> None:
    analytics = _fake_analytics()
    hand_history_visibility.install(analytics)
    hand_history_visibility.install(analytics)  # idempotent

    # Completed hand: the authorized participant receives every stored hand.
    done = analytics._detail_payload("done", 1)
    cards = {int(p["user_id"]): p["cards"] for p in done["players"]}
    assert cards == {
        1: ["As", "Kd"],
        2: ["Qc", "Jc"],
        3: ["7h", "7s"],
    }
    assert done["visibility"] == {
        "scope": "participant",
        "completed_hand_cards": "all_players",
    }
    assert len(done["actions"]) == 3

    # Active hand: even a participant still sees the original masked response.
    active = analytics._detail_payload("active", 1)
    active_cards = {int(p["user_id"]): p["cards"] for p in active["players"]}
    assert active_cards[1] == ["As", "Kd"]
    assert active_cards[2] == ["??", "??"]
    assert active_cards[3] == ["??", "??"]
    assert "visibility" not in active

    # Non-participant: original authorization failure must happen before raw-card lookup.
    try:
        analytics._detail_payload("done", 99)
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("non-participant could read completed hand history")

    exported = analytics._export_text("done", 1)
    assert "Recorded hand for ボブ: [Qc Jc]" in exported
    assert "Recorded hand for キャロル: [7h 7s]" in exported

    root = Path(__file__).resolve().parent
    app_js = (root / "materialized_v1244" / "static" / "app.js").read_text(encoding="utf-8")
    transformed = hand_history_visibility.transform_app_js(app_js)
    assert hand_history_visibility.HAND_HISTORY_VISIBILITY_MARKER in transformed
    assert "jj-hand-participant-grid" in transformed
    assert "ALL HANDS" in transformed
    assert "shown=cards" in transformed
    assert "全プレイヤーのホールカード・全アクション・ボード" in transformed
    assert "相手のホールカードは、ショーダウンで実際に公開された場合だけ表示します。" not in transformed
    assert hand_history_visibility.transform_app_js(transformed) == transformed

    styles = hand_history_visibility.transform_styles("")
    assert ".jj-hand-participant-grid" in styles
    assert hand_history_visibility.transform_styles(styles) == styles

    node = shutil.which("node")
    if node:
        target = Path(tempfile.mkdtemp(prefix="jj-hand-history-js-")) / "app.js"
        target.write_text(transformed, encoding="utf-8")
        subprocess.run([node, "--check", str(target)], check=True)

    print("JJ_HAND_HISTORY_VISIBILITY_SMOKE_OK")


if __name__ == "__main__":
    run()
