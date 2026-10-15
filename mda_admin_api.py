"""Admin-only cached MDA grid endpoint: one indexed read, zero live analysis.

Administrators can review privacy-filtered population data from all players.
This deliberately grants NO member/seat/opponent-specific feed and cannot
trigger a full-history database scan from a user request.
"""
from __future__ import annotations

import json
import os
from typing import Any

from fastapi import Depends, HTTPException, Query, Response

from mda_cache_contract import FORMAT, MAX_DOC_BYTES, cache_key


def _read_cached_grid(db: Any, key: str) -> dict | None:
    """The only DB operation in the request path is a cached-row lookup."""
    with db.connect() as con:
        try:
            row = con.execute(
                "SELECT payload_json FROM jj_mda_population_cache WHERE scope_key=?",
                (key,),
            ).fetchone()
        except Exception as exc:
            # A new release may precede the first offline snapshot publication.
            # Missing cache table is a harmless not-ready case; any other
            # database error must surface, not be silently masked.
            name = type(exc).__name__
            message = str(exc).lower()
            if name in ("UndefinedTable", "OperationalError") and (
                "jj_mda_population_cache" in message and
                ("does not exist" in message or "no such table" in message)
            ):
                return None
            raise
    if not row:
        return None
    raw = row["payload_json"]
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_DOC_BYTES:
        raise RuntimeError("invalid MDA cached payload size")
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get("format_version") != FORMAT:
        raise RuntimeError("invalid MDA cached payload format")
    return value


def install(app, server, db):
    @app.get("/api/admin/mda/grid")
    def mda_grid(
        response: Response,
        game: str = Query("Ring"),
        table_size: int = Query(6, ge=2, le=6),
        position: str = Query("BTN", max_length=8),
        admin=Depends(server.admin_user),
    ):
        # MDA v1 169-class/plus-range UI has been withdrawn. There is no
        # scientific basis to classify unseen classes as excluded or included.
        # This URL will never read any legacy range snapshot, even if an
        # operator had previously enabled its old environment flag.
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return {
            "status": "not_ready",
            "rollout": "legacy_range_retired",
            "message": "旧169ハンド推定は廃止しました。オンライン卓の行動頻度MDAへ移行中です。",
        }
