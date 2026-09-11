from __future__ import annotations

import tempfile
from pathlib import Path

from runtime_builder import RUNTIME_VERSION, build_runtime


def main() -> None:
    assert RUNTIME_VERSION == "1.24.2"
    with tempfile.TemporaryDirectory() as td:
        root = build_runtime(Path(td) / "runtime")
        app = (root / "static" / "app.js").read_text(encoding="utf-8")
        css = (root / "static" / "styles.css").read_text(encoding="utf-8")
        server = (root / "server.py").read_text(encoding="utf-8")

        # Touch-visible disabled reasons remain intact under the v1.24 renderer.
        assert "jjV123DisabledHints" in app
        assert "レイズ不可：" in app
        assert "Foldは誤操作防止で非表示" in app
        assert "jj-v123-disabled-hints" in css

        # Exact-context all-in confirmation remains authoritative.
        assert "jjV123AllinConfirmKey" in app
        assert "jjV123AllinKey(action,selected)" in app
        assert "hand.action_seat" in app
        assert "jjV123AllinConfirmKey!==confirmKey" in app

        # Exact seconds + glanceable progress meter remain available.
        assert "--jj-v123-clock-pct" in app
        assert "アクション残り${sec}秒" in app
        assert "--jj-v123-clock-pct" in css

        # WebSocket reconnect state remains visible while HTTP polling continues.
        assert "jjV123TableConnection" in app
        assert "再接続中 · 卓の更新を継続中" in app
        assert "jj-v123-table-connection" in css

        # Staged runout errors remain operationally visible.
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

        # Authoritative idempotency still protects duplicate actions.
        assert "_processed_action_ids" in server
        assert "payload.action_id" in server
        assert "jjV121ActionId" in app

        # v1.24 must be the last poker presentation owner. The v1.24.2 contrast
        # patch changes only home learning-card CSS and cache/version metadata.
        assert app.rfind("v1.24.0 unified online-poker presentation layer") > app.rfind("v1.23.0 final mobile interaction audit")

    print("v1.24 safety and interaction audit smoke: ok")


if __name__ == "__main__":
    main()
