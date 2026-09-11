from __future__ import annotations

import py_compile
import tempfile
from pathlib import Path

from runtime_builder import RUNTIME_VERSION, build_runtime


ROOT = Path(__file__).resolve().parent


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def main() -> None:
    # This is a feature-regression suite for the v1.24.3 product surfaces, not a
    # release-number gate. Later releases must keep these contracts intact.
    assert _version_tuple(RUNTIME_VERSION) >= (1, 24, 3)
    patch_source = (ROOT / "v54_patch.py").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as td:
        root = build_runtime(Path(td) / "runtime")
        app = (root / "static" / "app.js").read_text(encoding="utf-8")
        css = (root / "static" / "styles.css").read_text(encoding="utf-8")
        server = (root / "server.py").read_text(encoding="utf-8")
        index = (root / "static" / "index.html").read_text(encoding="utf-8")
        sw = (root / "static" / "sw.js").read_text(encoding="utf-8")

        marker = "v1.24.3 focused non-poker product UX"
        assert marker in app
        assert marker in css
        final = app.split(marker, 1)[1]

        # Home is now action-first instead of a flat feature catalogue.
        assert "今日の最優先" in final or "TODAY · PRIORITY" in final
        assert "今日のクイズをあと${remaining}問" in final
        assert "最初にやることを1つだけ表示しています" in final
        assert "jj-v1243-focus" in final
        assert "jj-v1243-metric" in final
        assert "RECOMMENDED REVIEW" in final
        assert "RECENT HANDS" in final
        assert "api('/home/overview')" in final

        # Daily Quiz shows server-owned progress/reward state and explicit review.
        assert "function jjV1243QuizHeader" in final
        assert "今日 +${fmt(p.earned)}pt" in final
        assert "今日の結果を見る" in final
        assert "あなたの回答" in final
        assert "正解" in final
        assert "jjV1243QuizAnswerValue" in final
        assert "data-jj-v1243-retry=\"quiz\"" in final
        assert "post('/quiz/answer'" in final

        # Ranking adds personal context using existing season/month APIs.
        assert "function jjV1243LoadRanking" in final
        assert "api('/rankings?season=fall')" in final
        assert "month=${encodeURIComponent(month)}" in final
        assert "ランキングの現在地" in final
        assert "ポイント内訳" in final
        assert "TOP 5" in final
        assert "次の順位" in final
        assert "台帳・クイズ等" in final

        # Shared states are reusable across all three surfaces.
        assert "const jjV1243State=" in final
        assert "const jjV1243Skeleton=" in final
        assert "data-jj-v1243-retry" in final
        for selector in (".jj-v1243-state", ".jj-v1243-skeleton-grid", ".jj-v1243-meter"):
            assert selector in css
        assert "prefers-reduced-motion:reduce" in css

        # The v1.24.3 layer itself must not redefine the poker action/table layer.
        v1243_layer = final.split("v1.24.4 analysis focus and decision-first review", 1)[0]
        for forbidden in ("#actionBar", "pokerTable", "doAction=", "/tables/${currentTableId}/action"):
            assert forbidden not in v1243_layer, forbidden

        # Existing modular endpoints are reused. v54_patch must not introduce a
        # new FastAPI route/reward path merely to support presentation changes.
        for endpoint in ("/home/overview", "/quiz/answer", "/rankings?season=fall"):
            assert endpoint in final, endpoint
        assert "@app.get(" not in patch_source
        assert "@app.post(" not in patch_source
        assert "@app.put(" not in patch_source
        assert "@app.delete(" not in patch_source

        # Release/cache identifiers are owned by the current release layer; only
        # require that reconstructed assets carry an explicit current contract.
        assert f'version="{RUNTIME_VERSION}"' in server or f'"version":"{RUNTIME_VERSION}"' in server
        assert 'request.url.query == "v=' in server
        assert "?v=" in index
        assert "jj-arena-live-v" in sw

    py_compile.compile(str(ROOT / "v54_patch.py"), doraise=True)
    py_compile.compile(str(ROOT / "runtime_builder.py"), doraise=True)
    print("JJ_V1243_NON_POKER_UI_SMOKE_OK")


if __name__ == "__main__":
    main()
