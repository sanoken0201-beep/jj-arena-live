from __future__ import annotations

import tempfile
from pathlib import Path

from runtime_builder import RUNTIME_VERSION, build_runtime


def main() -> None:
    assert RUNTIME_VERSION == "1.24.4"
    with tempfile.TemporaryDirectory() as td:
        root = build_runtime(Path(td) / "runtime")
        app = (root / "static" / "app.js").read_text(encoding="utf-8")
        css = (root / "static" / "styles.css").read_text(encoding="utf-8")
        server = (root / "server.py").read_text(encoding="utf-8")
        index = (root / "static" / "index.html").read_text(encoding="utf-8")
        sw = (root / "static" / "sw.js").read_text(encoding="utf-8")

        # Release/version/cache contract.
        assert 'version="1.24.4"' in server or '"version":"1.24.4"' in server
        assert 'request.url.query == "v=56"' in server
        assert "?v=56" in index
        assert "jj-arena-live-v56" in sw

        # Parent v1.24.3 non-poker product work must still be present.
        for marker in (
            "v1.24.3 focused non-poker product UX",
            "TODAY · PRIORITY",
            "ランキングの現在地",
            "今日の結果を見る",
        ):
            assert marker in app, marker

        # Analysis focus is descriptive and capped to three visible priorities.
        marker = "v1.24.4 analysis focus and decision-first review"
        assert marker in app
        final = app.split(marker, 1)[1]
        assert "今見るべきポイント" in final
        assert ".slice(0,3)" in final
        assert "solver判定ではありません" in final
        assert "関連ハンドを見る" in final
        assert "RELATED HANDS" in final
        assert "/analysis/focus-hands?metric=" in final
        for key in ("vpip_pfr_gap", "fold_to_3bet", "three_bet", "cbet", "position_vpip", "timeout"):
            assert key in final, key

        # Hand Review is decision-first but preserves full flow and review tools.
        assert "YOUR DECISIONS" in final
        assert "自分の意思決定" in final
        assert "jjV1244DecisionSummary" in final
        assert "Pot / Facing / サイズ / 時間" in final
        assert "全プレイヤーのアクションを見る" in final
        assert "ACTION FLOW" in app
        assert "テーブルリプレイ" in app
        assert "ブックマーク" in app
        assert "jjHandReviewForm" in app

        # Focus endpoint is read-only, user-scoped and excludes partial captures.
        endpoint_marker = "v1.24.4 analysis focus-hand endpoint"
        assert endpoint_marker in server
        endpoint = server.split(endpoint_marker, 1)[1]
        assert '@app.get("/api/analysis/focus-hands")' in endpoint
        assert 'p.user_id=?' in endpoint
        assert 'COALESCE(h.partial_capture,0)=0' in endpoint
        assert 'ORDER BY h.completed_at DESC' in endpoint
        assert 'limit = max(1, min(24' in endpoint
        for forbidden in ("INSERT INTO", "UPDATE jj_hand", "DELETE FROM", "solver", "ev_loss"):
            assert forbidden not in endpoint, forbidden

        # This release does not redefine the live poker action/settlement layer.
        for forbidden in (
            "doAction=function",
            "renderActionBar=function",
            "/tables/${currentTableId}/action",
            "_award_uncontested =",
            "advance_forced_runout =",
        ):
            assert forbidden not in final, forbidden

        # Responsive classes for the new analysis/review hierarchy exist.
        for selector in (
            ".jj-v1244-analysis-focus",
            ".jj-v1244-focus-grid",
            ".jj-v1244-focus-hand-grid",
            ".jj-v1244-decision-panel",
            ".jj-v1244-decision-list",
            ".jj-v1244-full-flow",
        ):
            assert selector in css, selector
        assert "@media" in css

    print("JJ_V1244_ANALYSIS_UX_SMOKE_OK")


if __name__ == "__main__":
    main()
