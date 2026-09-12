from __future__ import annotations

"""Smoke-test the final served poker labels and mobile focus-mode behavior."""

from pathlib import Path

from hand_history_visibility import (
    transform_app_js as transform_hand_history_app_js,
    transform_styles as transform_hand_history_styles,
)
from player_ux_asset_transform import transform_app_js as transform_player_app_js
from player_ux_clear_copy import transform_app_js as transform_clear_app_js
from player_ux_clear_copy import transform_styles as transform_clear_styles
from player_ux_phase2 import transform_app_js as transform_phase2_app_js
from player_ux_phase2 import transform_styles as transform_phase2_styles
from player_ux_phase3 import transform_app_js as transform_phase3_app_js
from player_ux_phase3 import transform_styles as transform_phase3_styles
from player_ux_phase4 import transform_app_js as transform_phase4_app_js
from player_ux_phase4 import transform_styles as transform_phase4_styles
from player_ux_phase5 import transform_app_js as transform_phase5_app_js
from player_ux_phase5 import transform_styles as transform_phase5_styles
from player_ux_phase5_mobile import transform_styles as transform_phase5_mobile_styles


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "materialized_v1244" / "static"


def main() -> None:
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    js = transform_hand_history_app_js(js)
    js = transform_phase5_app_js(
        transform_phase4_app_js(
            transform_phase3_app_js(
                transform_phase2_app_js(transform_player_app_js(js))
            )
        )
    )
    js = transform_clear_app_js(js)

    assert "卓を広く表示" in js
    assert "元の表示に戻す" in js
    assert "⚙ テーブル設定" in js
    assert "ハンド履歴" in js
    assert "観戦中 · 着席人数 ${active}/6" in js
    assert "持ち点 ${bb(hero.stack)} · 着席人数 ${active}/6" in js
    assert "着席者全員が「準備OK」を押すと開始します" in js
    assert "<b>テーブルに参加</b><span>持ち点150bbで着席します</span>" in js
    assert ">集中表示</button>" not in js
    assert ">JOIN TABLE</b>" not in js

    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    css = transform_hand_history_styles(css)
    css = transform_phase5_mobile_styles(
        transform_phase5_styles(
            transform_phase4_styles(
                transform_phase3_styles(transform_phase2_styles(css))
            )
        )
    )
    css = transform_clear_styles(css)
    assert "#pokerRoom #jjFocusModeToggle{display:none!important}" in css

    print("CLEAR_POKER_COPY_OK")


if __name__ == "__main__":
    main()
