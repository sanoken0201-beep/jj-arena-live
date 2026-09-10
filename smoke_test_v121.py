from __future__ import annotations

import json
import tempfile
from pathlib import Path

from runtime_builder import RUNTIME_VERSION, build_runtime


def main() -> None:
    assert RUNTIME_VERSION == "1.21.0"
    with tempfile.TemporaryDirectory() as td:
        root = build_runtime(Path(td) / "runtime")
        server = (root / "server.py").read_text(encoding="utf-8")
        engine = (root / "poker_engine.py").read_text(encoding="utf-8")
        appjs = (root / "static" / "app.js").read_text(encoding="utf-8")
        index = (root / "static" / "index.html").read_text(encoding="utf-8")
        sw = (root / "static" / "sw.js").read_text(encoding="utf-8")

        assert 'version="1.21.0"' in server
        assert "action_id: str | None" in server
        assert "_processed_action_ids" in server
        assert '"_processed_action_ids"' in engine
        assert "v1.21.0 learning and home hub" in appjs
        assert "action_id:jjV121ActionId()" in appjs
        assert "/analysis/learning" in appjs
        assert "/home/overview" in appjs
        assert "?v=49" in index
        assert "jj-arena-live-v49" in sw

        scope = {}
        exec(compile(engine, str(root / "poker_engine.py"), "exec"), scope)
        state = scope["blank_table_state"](table_id="table-a", name="A")
        state["_processed_action_ids"] = ["secret-receipt"]
        public = scope["public_state"](state, None)
        assert "_processed_action_ids" not in public
        json.dumps(public)

    import operations_learning
    import resilience
    assert callable(operations_learning.learning_payload)
    assert callable(resilience.backup_state)
    print("v1.21 smoke: ok")


if __name__ == "__main__":
    main()
