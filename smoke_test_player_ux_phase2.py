from __future__ import annotations

from pathlib import Path

from player_ux_asset_transform import transform_app_js as transform_phase1
from player_ux_phase2 import PHASE2_MARKER, leave_after_hand_transition, transform_app_js as transform_phase2


ROOT = Path(__file__).resolve().parent


def main() -> None:
    original = (ROOT / "materialized_v1244" / "static" / "app.js").read_text(encoding="utf-8")
    phase1 = transform_phase1(original)
    patched = transform_phase2(phase1)

    assert PHASE2_MARKER in patched
    assert transform_phase2(patched) == patched

    # Leave-after-hand is a lifecycle reservation, not a poker action. Nothing
    # about the current hand, stack, cards, fold state or turn is altered.
    state = {
        "status": "playing",
        "hand": {"id": "h1", "action_seat": 0},
        "seats": [
            {
                "user_id": 7,
                "seat": 0,
                "stack": 7250,
                "cards": ["As", "Kh"],
                "in_hand": True,
                "folded": False,
                "all_in": False,
                "round_bet": 300,
                "contributed": 300,
                "sit_out_next": True,
            }
        ],
    }
    before = {k: v for k, v in state["seats"][0].items() if k not in {"sit_out_next", "leave_after_hand"}}
    assert leave_after_hand_transition(state, 7, True) == "reserved"
    hero = state["seats"][0]
    after = {k: v for k, v in hero.items() if k not in {"sit_out_next", "leave_after_hand"}}
    assert before == after
    assert hero["leave_after_hand"] is True
    assert hero["sit_out_next"] is False
    assert leave_after_hand_transition(state, 7, False) == "cancelled"
    assert "leave_after_hand" not in hero
    state["status"] = "waiting"
    hero["in_hand"] = False
    assert leave_after_hand_transition(state, 7, True) == "leave_now"
    assert leave_after_hand_transition({"status": "waiting", "seats": []}, 7, False) == "left"

    assert "const jjV2Connection={mode:'idle',fresh:false" in patched
    assert "jjV2SetConnection('syncing',false)" in patched
    assert "jjV2SetConnection('reconnecting',false)" in patched
    assert "jjV2AcceptState('poll',previous)" in patched
    assert "最新の卓状態を同期中です。更新後に操作できます" in patched
    assert "リアルタイム接続" in patched and "HTTP同期中" in patched
    assert "最新 ${stamp}" in patched
    assert "jjV2PokerConfig?.action_timeout_seconds" in patched
    assert "(sec/45)*100" not in patched

    assert "時間切れ → ${jjV2TimeoutAction(logs,index)}（次ハンドから一時離席）" in patched
    assert "このハンド終了後に退席" in patched
    assert "退席予約中 · 現在のハンドはそのままプレイします" in patched
    assert "ハンド終了後の退席を取消" in patched
    assert "総ポット（卓全体）" in patched
    assert "レーキ（卓全体）" in patched
    assert "あなたの純損益" in patched
    assert "ランキング反映" in patched
    assert "data-jj-review-hand" in patched
    assert "await jjOpenHand(review.dataset.jjReviewHand)" in patched

    entry = (ROOT / "app.py").read_text(encoding="utf-8")
    assert '@app.post("/api/poker-config")' in entry
    assert 'inspect.signature(runtime_server.arm_action_deadline)' in entry
    assert '@app.post("/api/tables/{table_id}/leave-after-hand")' in entry
    assert "runtime_poker_engine.remove_player" in entry
    assert "runtime_server.save_table(state)" in entry
    assert "'/static/app.js?v=" in entry
    assert "jj-arena-live-v" in entry

    print("JJ_PLAYER_UX_PHASE2_SMOKE_OK")


if __name__ == "__main__":
    main()
