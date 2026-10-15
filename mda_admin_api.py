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

from mda_snapshot_cache import FORMAT, MAX_DOC_BYTES, cache_key


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
        # Defense in depth even if client nav was hidden by frontend CSS.
        try:
            key = cache_key(game, table_size, position)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Deployment-safe rollout: the newly deployed UI cannot publish
        # inferred population data until the administrator explicitly opts in.
        # This check happens AFTER the admin role dependency and BEFORE any SQL.
        if os.environ.get("JJ_MDA_ADMIN_ENABLED") != "1":
            return {
                "status": "disabled", "game": game,
                "table_size": table_size, "position": position,
                "message": "MDAの公開は運営の確認待ちです。",
            }
        doc = _read_cached_grid(db, key)
        if doc is None:
            return {
                "status": "not_ready", "game": game,
                "table_size": table_size, "position": position,
                "message": "MDAのスナップショットはまだ公開されていません。",
            }
        # Detect cache corruption or a mismatched scope instead of showing
        # other positions/format's data.
        if (
            doc.get("game") != game or
            doc.get("table_size") != table_size or
            doc.get("position") != position or
            len(doc.get("grid") or []) != 13 or
            any(len(row) != 13 for row in doc["grid"])
        ):
            raise HTTPException(503, "MDA cache cohort is inconsistent")
        return {"status": "ok", **doc}
