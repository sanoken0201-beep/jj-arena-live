from __future__ import annotations

import tempfile
from pathlib import Path

from runtime_builder import RUNTIME_VERSION, build_runtime


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def main() -> None:
    assert _version_tuple(RUNTIME_VERSION) >= (1, 23, 0)
    with tempfile.TemporaryDirectory() as td:
        root = build_runtime(Path(td) / "runtime")
        app = (root / "static" / "app.js").read_text(encoding="utf-8")
        css = (root / "static" / "styles.css").read_text(encoding="utf-8")
        server = (root / "server.py").read_text(encoding="utf-8")

        assert "jjV123DisabledHints" in app
        assert "レイズ不可：" in app
        assert "Foldは誤操作防止で非表示" in app
        assert "jj-v123-disabled-hints" in css
        assert "jjV123AllinConfirmKey" in app
        assert "jjV123AllinKey(action,selected)" in app
        assert "hand.action_seat" in app
        assert "jjV123AllinConfirmKey!==confirmKey" in app
        assert "--jj-v123-clock-pct" in app
        assert "アクション残り${sec}秒" in app
        assert "--jj-v123-clock-pct" in css
        assert "jjV123TableConnection" in app
        assert "再接続中 · 卓の更新を継続中" in app
        assert "jj-v123-table-connection" in css
        assert '"forced_runout"' in server
        assert "_jj_v123_resilience.record_error" in server
        assert "v1.23.0 forced-runout operational logging" in server

        marker = "v1.23.0 reconstructed-server scheduler compatibility final"
        assert marker in server
        final_scheduler = server.split(marker, 1)[1]
        assert "db.FIXED_TABLES" in final_scheduler
        assert "get_table_lock(table_id)" in final_scheduler
        assert "hub.broadcast(table_id)" in final_scheduler
        assert "FIXED_TABLE_IDS" not in final_scheduler
        assert "table_locks[table_id]" not in final_scheduler
        assert "broadcast_table(table_id)" not in final_scheduler
        assert "arm_action_deadline(state)" not in final_scheduler
        assert "_processed_action_ids" in server
        assert "payload.action_id" in server
        assert "jjV121ActionId" in app
        assert app.rfind("v1.24.0 unified online-poker presentation layer") > app.rfind("v1.23.0 final mobile interaction audit")
        assert "v1.24.3 focused non-poker product UX" in app

    print("poker safety and interaction audit smoke: ok")


if __name__ == "__main__":
    main()
