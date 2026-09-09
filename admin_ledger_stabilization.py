from __future__ import annotations

import uuid
from typing import Any

from fastapi import Depends, HTTPException

MANUAL_KINDS = ("credit", "collection", "reversal")
REVERSIBLE_KINDS = ("credit", "collection")
QUIZ_KIND = "quiz_reward"


def _ledger_by_name(db, server, *, month: str | None, season: str) -> dict[str, dict[str, float]]:
    start, end = _bounds(server, season)
    where = "WHERE l.effective_at>=? AND l.effective_at<?"
    params: list[Any] = [start, end]
    if month:
        where += " AND substr(l.effective_at,1,7)=?"
        params.append(month)
    with db.connect() as con:
        rows = con.execute(
            f"""
            SELECT COALESCE(NULLIF(u.ranking_name,''),u.name) name,
                   SUM(l.amount) ledger_points,
                   SUM(CASE WHEN l.kind IN ('credit','collection','reversal') THEN l.amount ELSE 0 END) manual_points,
                   SUM(CASE WHEN l.kind='quiz_reward' THEN l.amount ELSE 0 END) quiz_points
            FROM point_ledger l
            JOIN users u ON u.id=l.user_id
            {where}
            GROUP BY COALESCE(NULLIF(u.ranking_name,''),u.name)
            """,
            params,
        ).fetchall()
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        ledger = float(row["ledger_points"] or 0)
        manual = float(row["manual_points"] or 0)
        quiz = float(row["quiz_points"] or 0)
        out[str(row["name"])] = {
            "ledger_points": round(ledger, 2),
            "admin_points": round(manual, 2),
            "quiz_points": round(quiz, 2),
            "other_ledger_points": round(ledger - manual - quiz, 2),
        }
    return out


def _bounds(server, season: str) -> tuple[str, str]:
    start = getattr(server, "FALL_SEASON_START", "2026-09-01")
    end = getattr(server, "FALL_SEASON_END", "2027-04-01")
    return (start, end) if season == "fall" else ("0000-01-01", start)


def install(app, admin_console) -> None:
    """Correct ledger semantics without changing historical ledger rows.

    The v1.18 admin console predated quiz rewards and therefore treated every
    point_ledger row as an administrator adjustment. v1.18.6 added
    ``quiz_reward`` rows. Total ranking points were correct, but the admin UI
    mislabeled quiz rewards as manual adjustments and could offer reversal of
    non-manual rewards. This compatibility layer keeps total rankings intact
    while separating ledger categories and restricting the manual ledger API.
    """
    if getattr(app.state, "jj_admin_ledger_stabilized", False):
        return
    app.state.jj_admin_ledger_stabilized = True

    import db
    import server

    original_rankings = admin_console._rankings

    def rankings(db_module, server_module, month=None, season="fall"):
        rows = original_rankings(db_module, server_module, month, season)
        split = _ledger_by_name(db_module, server_module, month=month, season=season)
        for row in rows:
            categories = split.get(
                str(row["name"]),
                {"ledger_points": 0.0, "admin_points": 0.0, "quiz_points": 0.0, "other_ledger_points": 0.0},
            )
            # Preserve the original total: it already includes every ledger row.
            row.update(categories)
        return rows

    admin_console._rankings = rankings

    def remove_route(path: str, method: str) -> None:
        method = method.upper()
        app.router.routes[:] = [
            route
            for route in app.router.routes
            if not (
                str(getattr(route, "path", "")) == path
                and method in set(getattr(route, "methods", set()) or set())
            )
        ]

    remove_route("/api/admin/console/overview", "GET")
    remove_route("/api/admin/console/points", "GET")
    remove_route("/api/admin/console/points/{txid}/reverse", "POST")

    def overview(user=Depends(server.admin_user)):
        start, end = _bounds(server, "fall")
        with db.connect() as con:
            accounts = con.execute(
                """
                SELECT COUNT(*) total,
                       SUM(CASE WHEN COALESCE(disabled,0)=0 THEN 1 ELSE 0 END) active,
                       SUM(CASE WHEN COALESCE(disabled,0)<>0 THEN 1 ELSE 0 END) disabled,
                       SUM(CASE WHEN COALESCE(club_verified,0)<>0 THEN 1 ELSE 0 END) verified
                FROM users
                """
            ).fetchone()
            manual = con.execute(
                """
                SELECT COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) credited,
                       COALESCE(SUM(CASE WHEN amount<0 THEN -amount ELSE 0 END),0) collected,
                       COUNT(*) transactions
                FROM point_ledger
                WHERE effective_at>=? AND effective_at<?
                  AND kind IN ('credit','collection','reversal')
                """,
                (start, end),
            ).fetchone()
            quiz = con.execute(
                """
                SELECT COALESCE(SUM(amount),0) points, COUNT(*) transactions
                FROM point_ledger
                WHERE effective_at>=? AND effective_at<? AND kind='quiz_reward'
                """,
                (start, end),
            ).fetchone()
            dup = con.execute(
                """
                SELECT COALESCE(NULLIF(ranking_name,''),name) ranking_name,COUNT(*) n
                FROM users
                WHERE COALESCE(disabled,0)=0
                GROUP BY COALESCE(NULLIF(ranking_name,''),name)
                HAVING COUNT(*)>1
                ORDER BY n DESC,ranking_name LIMIT 20
                """
            ).fetchall()
            recent = con.execute(
                """
                SELECT a.id,a.action,a.detail_json,a.created_at,u.name actor_name,t.name target_name
                FROM admin_audit_log a
                LEFT JOIN users u ON u.id=a.actor_id
                LEFT JOIN users t ON t.id=a.target_user_id
                ORDER BY a.id DESC LIMIT 8
                """
            ).fetchall()
        ranks = admin_console._rankings(db, server, season="fall")
        return {
            "accounts": {
                "total": int(accounts["total"] or 0),
                "active": int(accounts["active"] or 0),
                "disabled": int(accounts["disabled"] or 0),
                "verified": int(accounts["verified"] or 0),
            },
            "ledger": {
                "credited": round(float(manual["credited"] or 0), 2),
                "collected": round(float(manual["collected"] or 0), 2),
                "transactions": int(manual["transactions"] or 0),
            },
            "quiz": {
                "points": round(float(quiz["points"] or 0), 2),
                "transactions": int(quiz["transactions"] or 0),
            },
            "season": {"start": start, "end_exclusive": end},
            "ranking_total": round(sum(float(row["points"]) for row in ranks), 2),
            "duplicate_mappings": [dict(row) for row in dup],
            "recent_audit": [dict(row) for row in recent],
        }

    def ledger(user_id: int | None = None, limit: int = 200, user=Depends(server.admin_user)):
        limit = max(1, min(int(limit), 500))
        params: list[Any] = []
        where = "WHERE l.kind IN ('credit','collection','reversal')"
        if user_id:
            where += " AND l.user_id=?"
            params.append(user_id)
        params.append(limit)
        with db.connect() as con:
            rows = con.execute(
                f"""
                SELECT l.id,l.user_id,l.amount,l.kind,l.reason,l.effective_at,l.created_at,l.reversal_of,
                       u.name user_name,COALESCE(NULLIF(u.ranking_name,''),u.name) ranking_name,
                       a.name actor_name,
                       CASE WHEN EXISTS(SELECT 1 FROM point_ledger rv WHERE rv.reversal_of=l.id) THEN 1 ELSE 0 END reversed
                FROM point_ledger l
                JOIN users u ON u.id=l.user_id
                LEFT JOIN users a ON a.id=l.created_by
                {where}
                ORDER BY l.created_at DESC LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def reverse(txid: str, user=Depends(server.admin_user)):
        with db.connect() as con:
            original = con.execute("SELECT * FROM point_ledger WHERE id=?", (txid,)).fetchone()
            if not original:
                raise HTTPException(404, "transaction not found")
            if str(original["kind"]) not in REVERSIBLE_KINDS:
                raise HTTPException(400, "管理者による振込・回収だけを取消できます")
            if original["reversal_of"]:
                raise HTTPException(400, "取消取引は再取消できません")
            if con.execute("SELECT 1 FROM point_ledger WHERE reversal_of=?", (txid,)).fetchone():
                raise HTTPException(409, "すでに取消済みです")
            reversal_id = "pt-" + uuid.uuid4().hex
            amount = -float(original["amount"])
            con.execute(
                """
                INSERT INTO point_ledger(
                    id,user_id,amount,kind,reason,effective_at,created_by,created_at,reversal_of
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    reversal_id,
                    original["user_id"],
                    amount,
                    "reversal",
                    f"取消: {original['reason']}",
                    original["effective_at"],
                    user["id"],
                    admin_console._now(db),
                    txid,
                ),
            )
        admin_console._audit(
            db,
            int(user["id"]),
            "point.reverse",
            int(original["user_id"]),
            transaction_id=reversal_id,
            reversal_of=txid,
            amount=amount,
        )
        return {"id": reversal_id, "reversal_of": txid, "amount": amount}

    app.add_api_route("/api/admin/console/overview", overview, methods=["GET"], name="admin_overview_v190")
    app.add_api_route("/api/admin/console/points", ledger, methods=["GET"], name="admin_manual_ledger_v190")
    app.add_api_route(
        "/api/admin/console/points/{txid}/reverse",
        reverse,
        methods=["POST"],
        name="admin_manual_ledger_reverse_v190",
    )
