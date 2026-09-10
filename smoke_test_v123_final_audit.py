from __future__ import annotations

import tempfile
from pathlib import Path

from runtime_builder import RUNTIME_VERSION, build_runtime


def main() -> None:
    assert RUNTIME_VERSION == "1.23.0"
    with tempfile.TemporaryDirectory() as td:
        root = build_runtime(Path(td) / "runtime")
        app = (root / "static" / "app.js").read_text(encoding="utf-8")
        css = (root / "static" / "styles.css").read_text(encoding="utf-8")
        server = (root / "server.py").read_text(encoding="utf-8")

        # Touch-visible disabled reasons, not desktop-only title tooltips.
        assert "jjV123DisabledHints" in app
        assert "レイズ不可：" in app
        assert "Foldは誤操作防止で非表示" in app
        assert "jj-v123-disabled-hints" in css

        # An armed all-in confirmation belongs only to the exact current context.
        assert "jjV123AllinConfirmKey" in app
        assert "jjV123AllinKey(action,selected)" in app
        assert "hand.action_seat" in app
        assert "jjV123AllinConfirmKey!==confirmKey" in app

        # Clock remains exact in seconds but is also glanceable on a phone.
        assert "--jj-v123-clock-pct" in app
        assert "アクション残り${sec}秒" in app
        assert "--jj-v123-clock-pct" in css

        # WebSocket reconnect state is visible while fallback polling continues.
        assert "jjV123TableConnection" in app
        assert "再接続中 · 卓の更新を継続中" in app
        assert "jj-v123-table-connection" in css

        # A failed staged runout cannot silently strand a production hand.
        assert '"forced_runout"' in server
        assert "_jj_v123_resilience.record_error" in server
        assert "v1.23.0 forced-runout operational logging" in server

        # The existing authoritative double-submit protection remains present.
        assert "_processed_action_ids" in server
        assert "payload.action_id" in server
        assert "jjV121ActionId" in app

    print("v1.23 final mobile audit smoke: ok")


if __name__ == "__main__":
    main()
