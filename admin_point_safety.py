"""Exactly-once manual point requests, committed with their audit record."""
from __future__ import annotations

import json
import uuid

from fastapi import HTTPException


def ensure_schema(db):
    with db.connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS admin_point_requests(
            actor_id INTEGER NOT NULL REFERENCES users(id),
            request_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            response_json TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY(actor_id,request_id)
        )""")


def apply_point(db, console, p, user):
    direction = p.direction.strip().lower()
    if direction not in {"credit", "debit"}:
        raise HTTPException(400, "direction must be credit or debit")
    amount = console._pt(p.amount)
    if amount <= 0:
        raise HTTPException(400, "0より大きいポイントを入力してください")
    # An omitted effective_at stays omitted in the identity, not a new timestamp
    # on every retry. The resolved timestamp is stored in the original response.
    identity = json.dumps({"user_id": p.user_id, "direction": direction,
        "amount": amount, "reason": p.reason.strip(),
        "effective_at": p.effective_at or None}, sort_keys=True, ensure_ascii=False)
    with db.connect() as con:
        # First statement takes the SQLite writer lock / PostgreSQL unique-key
        # lock. A concurrent retry waits for commit and sees the saved response.
        claimed = con.execute("""INSERT INTO admin_point_requests
            (actor_id,request_id,payload_json,created_at) VALUES (?,?,?,?)
            ON CONFLICT(actor_id,request_id) DO NOTHING""",
            (user["id"], p.request_id, identity, console._now(db))).rowcount
        if not claimed:
            row = con.execute("""SELECT payload_json,response_json FROM admin_point_requests
                WHERE actor_id=? AND request_id=?""", (user["id"], p.request_id)).fetchone()
            if row["payload_json"] != identity:
                raise HTTPException(409, "同じ操作IDで異なる内容は送信できません")
            if not row["response_json"]:
                raise HTTPException(409, "処理結果を確認できません。管理台帳を確認してください")
            return json.loads(row["response_json"])
        limit = con.execute("SELECT value FROM app_settings WHERE key='manual_adjustment_limit'").fetchone()
        cap = float(limit["value"]) if limit else 100000
        if amount > cap:
            raise HTTPException(400, f"1回の操作は{cap:g}pt以下にしてください")
        target = con.execute("SELECT id FROM users WHERE id=? AND deleted_at IS NULL", (p.user_id,)).fetchone()
        if not target:
            raise HTTPException(404, "user not found")
        signed = amount if direction == "credit" else -amount
        effective = console._effective(p.effective_at, db)
        tx = "pt-" + uuid.uuid4().hex
        con.execute("""INSERT INTO point_ledger
            (id,user_id,amount,kind,reason,effective_at,created_by,created_at,reversal_of)
            VALUES (?,?,?,?,?,?,?,?,NULL)""", (tx,p.user_id,signed,
            "credit" if signed > 0 else "collection",p.reason.strip(),effective,user["id"],console._now(db)))
        console._audit(db,int(user["id"]),"point.credit" if signed > 0 else "point.collection",
            p.user_id,con=con,transaction_id=tx,amount=signed,reason=p.reason.strip(),effective_at=effective)
        result = {"id": tx, "user_id": p.user_id, "amount": signed, "effective_at": effective}
        con.execute("UPDATE admin_point_requests SET response_json=? WHERE actor_id=? AND request_id=?",
                    (json.dumps(result),user["id"],p.request_id))
    return result
