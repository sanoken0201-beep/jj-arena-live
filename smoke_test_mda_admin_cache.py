"""MDA admin cache contract, role gate, atomic publication and no live SQL scans."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import os
from unittest.mock import patch
import sqlite3
from types import SimpleNamespace

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from mda_admin_api import install
from mda_cache_contract import POSITIONS_BY_SIZE as CACHE_POSITIONS
from mda_snapshot_cache import FORMAT, cache_key, snapshot_documents
from mda_ranges import POSITIONS_BY_SIZE, expand_plus


def _reports():
    ring = {
        "format_version": "mda-all-players-v1", "game": "Ring",
        "source_ring_tables": ["jj-table-a", "jj-table-b"],
        "coverage": {"complete_scan": True},
        "cohorts_by_players_dealt_in": {
            "6": {
                "completed_hands_used": 1234,
                "positions": {"BTN": {"rfi_range": {
                    "status": "ok",
                    "cells": {
                        "K5o": {
                            "status": "observed", "opportunities": 30,
                            "open_frequency": 40, "smoothed_frequency": 41,
                            "wilson_95_percent": [18, 62],
                        }
                    },
                    "hypotheses": [{
                        "notation": "K5o+", "status": "seed_replicated",
                        "candidate_classes": list(expand_plus("K5o+")),
                        "has_counterevidence": False,
                    }],
                }}}
            }
        },
    }
    sitngo = {
        "format_version": "mda-sitngo-rfi-v1", "game": "Sit&Go",
        "source": "sitngo_hands",
        "coverage": {"complete_scan": True},
        "cohorts_by_players_dealt_in": {},
    }
    return ring, sitngo


def _cell(doc, cls):
    return next(x for row in doc["grid"] for x in row if x["class"] == cls)


def _db():
    raw = sqlite3.connect(":memory:", check_same_thread=False)
    raw.row_factory = sqlite3.Row
    raw.execute(
        """CREATE TABLE jj_mda_population_cache(
               scope_key TEXT PRIMARY KEY,
               payload_json TEXT,
               generated_at TEXT)"""
    )
    return raw


def _server():
    def get_user(x_test_role: str | None = Header(None)):
        if x_test_role not in ("admin", "member"):
            raise HTTPException(401, "auth required")
        return {"role": x_test_role}

    def admin_user(user=Depends(get_user)):
        if user["role"] != "admin":
            raise HTTPException(403, "admin only")
        return user
    return SimpleNamespace(admin_user=admin_user)


class DB:
    def __init__(self, raw):
        self.raw = raw
        self.query_count = 0
    def connect(self):
        self.query_count += 1
        return self.raw


def run():
    assert cache_key("Ring", 6, "BTN") == "Ring:6:BTN"
    assert CACHE_POSITIONS == POSITIONS_BY_SIZE, "lightweight web contract drifted from offline analyzer"
    # The live route must not import DB-scanning analyzers just to serve
    # one cached row. Keep this check in a fresh interpreter.
    import subprocess, sys
    proc = subprocess.run(
        [sys.executable, "-c",
         "import sys, mda_admin_api; assert 'mda_all_players_offline_audit' not in sys.modules; assert 'mda_sitngo_offline_audit' not in sys.modules"],
        cwd=str(Path(__file__).resolve().parent), capture_output=True, text=True,
        timeout=15,
    )
    assert proc.returncode == 0, proc.stderr
    for args in (("Ring", 6, "BTN/SB"), ("Ring", 7, "BTN"), ("Unknown", 6, "BTN")):
        try:
            cache_key(*args)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid cohort key accepted")
    ring, sitngo = _reports()
    stamp = datetime(2026, 10, 15, tzinfo=timezone.utc).isoformat()
    docs = snapshot_documents(ring, sitngo, generated_at=stamp)
    assert len(docs) == 2 * sum(map(len, POSITIONS_BY_SIZE.values())) == 40
    one = docs["Ring:6:BTN"]
    assert one["format_version"] == FORMAT
    assert one["data_scope"] == "complete_history_snapshot"
    assert one["completed_hands_used"] == 1234
    assert len(one["grid"]) == 13
    assert _cell(one, "K5o")["open_frequency"] == 40
    assert _cell(one, "K6o")["status"] == "hypothesis"
    assert _cell(one, "K6o")["open_frequency"] is None
    assert _cell(one, "K9s")["status"] == "unknown"
    assert docs["Sit&Go:6:BTN"]["range_status"] == "insufficient_sample"
    for entry in docs.values():
        serialized = json.dumps(entry)
        assert all(secret not in serialized for secret in (
            "actor_id", "user_id", "hand_id", "hole_cards_json", "secret",
        ))
    # Publishing old Table-A-only or invented tournament sources must fail,
    # even when their reports claim a complete scan.
    for altered_ring, altered_sng in (
        (dict(ring, source_ring_tables=["jj-table-a"]), sitngo),
        (dict(ring, source_ring_tables=["jj-table-b"]), sitngo),
        (ring, dict(sitngo, source="wrong_table")),
    ):
        try:
            snapshot_documents(altered_ring, altered_sng, generated_at=stamp)
        except ValueError:
            pass
        else:
            raise AssertionError("unverified source coverage entered cache")

    partial = dict(ring, coverage={"complete_scan": False})
    try:
        snapshot_documents(partial, sitngo, generated_at=stamp)
    except ValueError:
        pass
    else:
        raise AssertionError("partial history was published")

    # Changing old observed seed to unknown must withdraw its plus candidates.
    revised = json.loads(json.dumps(ring))
    revised["cohorts_by_players_dealt_in"]["6"]["positions"]["BTN"]["rfi_range"]["cells"]["K5o"] = {"status":"unknown"}
    updated = snapshot_documents(revised, sitngo, generated_at=stamp)
    assert _cell(updated["Ring:6:BTN"], "K5o")["status"] == "unknown"
    assert _cell(updated["Ring:6:BTN"], "K6o")["status"] == "unknown"

    # Legacy dashboard endpoint is irrevocably disabled, regardless of
    # a previously-enabled environment flag or existing persisted cache.
    app = FastAPI()
    db = DB(_db())
    install(app, _server(), db)
    client = TestClient(app)
    endpoint = "/api/admin/mda/grid?game=Ring&table_size=6&position=BTN"
    assert client.get(endpoint).status_code == 401
    assert client.get(endpoint, headers={"x-test-role": "member"}).status_code == 403
    assert db.query_count == 0
    for setting in ("", "0", "1"):
        with patch.dict(os.environ, {"JJ_MDA_ADMIN_ENABLED": setting}):
            response = client.get(endpoint, headers={"x-test-role": "admin"})
            assert response.status_code == 200
            assert response.json()["status"] == "not_ready"
            assert response.json()["rollout"] == "legacy_range_retired"
            assert response.headers["cache-control"] == "private, no-store"
            assert db.query_count == 0, "legacy range cache was queried"

    # Browser view still loads lazily but its retired API cannot return data.
    root = Path(__file__).resolve().parent / "materialized_v1244" / "static"
    html = (root / "index.html").read_text(encoding="utf-8")
    js = (root / "mda-view.js").read_text(encoding="utf-8")
    css = (root / "mda-view.css").read_text(encoding="utf-8")
    app_js = (root / "app.js").read_text(encoding="utf-8")
    assert 'data-view="mda"' in html
    assert 'id="mdaView" class="view admin-only"' in html
    assert 'mda-view.js?v=1' in html and 'mda-view.css?v=1' in html
    assert "mda:['POPULATION MDA','MDA分析']" in app_js
    assert "MutationObserver" in js and "active-view" in js
    assert "textContent" in js and ".innerHTML" not in js
    assert "setInterval(" not in js and "new WebSocket(" not in js
    assert ".mda-matrix" in css and "overflow-x:auto" in css
    db.raw.close()
    print("smoke_test_mda_admin_cache: PASS")


if __name__ == "__main__":
    run()
