from __future__ import annotations

import asyncio
from pathlib import Path

import resilience
import runtime_performance


ROOT = Path(__file__).resolve().parent


class FakeServer:
    class Hub:
        connections = {
            "jj-table-a": [(object(), 1), (object(), 2)],
            "jj-table-b": [(object(), 3)],
            "empty": [],
        }

    hub = Hub()


class FakePostgresDB:
    IS_POSTGRES = True


class FakeSQLiteDB:
    IS_POSTGRES = False


class FakePool:
    def get_stats(self):
        return {
            "pool_min": 1,
            "pool_max": 4,
            "pool_size": 3,
            "pool_available": 2,
            "requests_waiting": 1,
            "requests_num": 40,
            "requests_errors": 2,
            "usage_ms": 125,
            "secret_conninfo": "must-not-leak",
        }


def main() -> None:
    resilience._API_LATENCY_MS.clear()
    resilience._API_LATENCY_MS.extend([10.0, 20.0, 30.0, 40.0])
    latency = resilience.api_latency_snapshot()
    assert latency == {
        "samples": 4,
        "window": 500,
        "p50_ms": 25.0,
        "p95_ms": 38.5,
        "max_ms": 40.0,
    }

    ws = resilience.websocket_snapshot(FakeServer)
    assert ws["connections"] == 3
    assert ws["by_table"] == {"jj-table-a": 2, "jj-table-b": 1}

    sqlite = resilience.db_pool_snapshot(FakeSQLiteDB)
    assert sqlite == {"backend": "sqlite", "enabled": False, "active": False}

    original_pool = runtime_performance._POOL
    try:
        runtime_performance._POOL = FakePool()
        pg = resilience.db_pool_snapshot(FakePostgresDB)
    finally:
        runtime_performance._POOL = original_pool
    assert pg["backend"] == "postgres" and pg["enabled"] is True and pg["active"] is True
    assert pg["pool_available"] == 2 and pg["pool_size"] == 3
    assert pg["requests_waiting"] == 1
    assert "secret_conninfo" not in pg

    probe = asyncio.run(resilience.event_loop_probe_ms())
    assert probe >= 0

    source = (ROOT / "resilience.py").read_text(encoding="utf-8")
    assert 'request.url.path.startswith("/api/")' in source
    assert "_API_LATENCY_MS.append" in source
    assert '"runtime": runtime' in source

    admin = (ROOT / "admin_static" / "ops_dashboard.js").read_text(encoding="utf-8")
    for marker in ("API latency", "WebSocket", "DB pool", "Event loop", "event_loop_probe_ms"):
        assert marker in admin, marker
    assert "user_id" not in admin
    assert "hand_id" not in admin
    assert "cards" not in admin

    admin_patch = (ROOT / "admin_copy_patch.py").read_text(encoding="utf-8")
    from admin_copy_patch import ADMIN_ASSET_VERSION
    assert int(ADMIN_ASSET_VERSION) >= 127

    print("JJ_RUNTIME_OBSERVABILITY_OK")


if __name__ == "__main__":
    main()
