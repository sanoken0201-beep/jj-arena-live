from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import db
from poker_engine import apply_action, blank_table_state, public_state, remove_player, seat_player, start_hand, legal_actions

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(timeout_loop())
    try:
        yield
    finally:
        task.cancel()

app = FastAPI(title="JJ Arena Live", version="1.1.0", lifespan=lifespan)
db.init_db()


def bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def current_user(authorization: str | None = Header(default=None)):
    user = db.get_user_by_token(bearer(authorization))
    if not user:
        raise HTTPException(401, "authentication required")
    return user


def admin_user(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "admin only")
    return user


class Signup(BaseModel):
    name: str = Field(min_length=1, max_length=30)
    email: str = Field(min_length=5, max_length=200)
    password: str = Field(min_length=6, max_length=200)


class Login(BaseModel):
    email: str
    password: str


class PointEntry(BaseModel):
    name: str
    date: str
    remaining: int = Field(ge=0)
    reentries: int = Field(ge=0, le=50)
    initial: int = Field(gt=0)
    game_type: str = "ring"


class ScheduleIn(BaseModel):
    date: str
    time: str
    room: str = Field(min_length=1, max_length=100)
    title: str = Field(default="JJ活動", max_length=120)
    note: str = Field(default="", max_length=1000)


class AnnouncementIn(BaseModel):
    kind: str = "club"
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=5000)
    url: str = Field(default="", max_length=1000)
    date: str


class ThreadIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class SeatIn(BaseModel):
    seat: int = Field(ge=0, le=5)


class ActionIn(BaseModel):
    action: str
    amount: int | None = None


class ChatIn(BaseModel):
    body: str = Field(min_length=1, max_length=500)


@app.get("/api/health")
def health():
    return {"ok": True, "service": "JJ Arena Live"}


@app.post("/api/auth/signup")
def signup(payload: Signup):
    email = payload.email.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(400, "invalid email")
    try:
        password_hash = db.hash_password(payload.password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    try:
        with db.connect() as con:
            uid = db.insert_returning_id(con,
                "INSERT INTO users(name,email,password_hash,role,arena_chips,xp,created_at) VALUES (?,?,?,?,?,?,?)",
                (payload.name.strip(), email, password_hash, "member", 0, 0, db.utcnow()),
            )
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(409, "email already registered")
        raise
    token = db.create_session(uid)
    return {"token": token, "user": user_payload(uid)}


@app.post("/api/auth/login")
def login(payload: Login):
    with db.connect() as con:
        row = con.execute("SELECT * FROM users WHERE lower(email)=?", (payload.email.strip().lower(),)).fetchone()
    if not row or not db.verify_password(payload.password, row["password_hash"]):
        raise HTTPException(401, "email or password is incorrect")
    token = db.create_session(row["id"])
    return {"token": token, "user": user_payload(row["id"])}


@app.post("/api/auth/logout")
def logout(authorization: str | None = Header(default=None), user=Depends(current_user)):
    db.delete_session(bearer(authorization))
    return {"ok": True}


def user_payload(uid: int):
    with db.connect() as con:
        row = con.execute("SELECT id,name,email,role,arena_chips,xp,created_at FROM users WHERE id=?", (uid,)).fetchone()
    return dict(row)


@app.get("/api/me")
def me(user=Depends(current_user)):
    return user_payload(user["id"])


@app.get("/api/rankings")
def rankings(month: str | None = None, user=Depends(current_user)):
    where = "WHERE name != '運営調整'"
    params: list[Any] = []
    if month:
        where += " AND substr(date,1,7)=?"
        params.append(month)
    with db.connect() as con:
        rows = con.execute(
            f"""
            SELECT name, SUM(points) AS points, COUNT(*) AS games, MAX(points) AS best,
                   SUM(CASE WHEN points>0 THEN 1 ELSE 0 END) AS wins
            FROM entries {where}
            GROUP BY name
            ORDER BY points DESC, best DESC, name ASC
            """,
            params,
        ).fetchall()
    return [dict(r) | {"rank": i + 1} for i, r in enumerate(rows)]


@app.get("/api/entries")
def entries(limit: int = 40, user=Depends(current_user)):
    limit = max(1, min(limit, 200))
    with db.connect() as con:
        rows = con.execute("SELECT * FROM entries ORDER BY date DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/entries")
def add_entry(payload: PointEntry, user=Depends(admin_user)):
    points = payload.remaining - (payload.reentries + 1) * payload.initial
    eid = "live-" + uuid.uuid4().hex
    game = f"{payload.initial}/ {'tournament' if payload.game_type == 'tournament' else 'ring'}"
    with db.connect() as con:
        con.execute(
            "INSERT INTO entries(id,date,name,remaining,reentries,initial,points,game,game_type,source,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (eid, payload.date, payload.name.strip(), payload.remaining, payload.reentries, payload.initial, points, game, payload.game_type, "JJ Arena Live", user["id"], db.utcnow()),
        )
    return {"id": eid, "points": points}


@app.get("/api/schedules")
def schedules(user=Depends(current_user)):
    with db.connect() as con:
        rows = con.execute("SELECT s.*,u.name AS creator FROM schedules s LEFT JOIN users u ON u.id=s.created_by ORDER BY date,time").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/schedules")
def add_schedule(payload: ScheduleIn, user=Depends(current_user)):
    with db.connect() as con:
        new_id = db.insert_returning_id(con,
            "INSERT INTO schedules(date,time,room,title,note,created_by,created_at) VALUES (?,?,?,?,?,?,?)",
            (payload.date, payload.time, payload.room.strip(), payload.title.strip() or "JJ活動", payload.note.strip(), user["id"], db.utcnow()),
        )
    return {"id": new_id}


@app.get("/api/announcements")
def announcements(user=Depends(current_user)):
    with db.connect() as con:
        rows = con.execute("SELECT a.*,u.name AS creator FROM announcements a LEFT JOIN users u ON u.id=a.created_by ORDER BY date DESC,id DESC").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/announcements")
def add_announcement(payload: AnnouncementIn, user=Depends(admin_user)):
    if payload.url and not payload.url.lower().startswith(("https://", "http://")):
        raise HTTPException(400, "URL must start with http:// or https://")
    with db.connect() as con:
        new_id = db.insert_returning_id(con,
            "INSERT INTO announcements(kind,title,body,url,date,created_by,created_at) VALUES (?,?,?,?,?,?,?)",
            (payload.kind, payload.title.strip(), payload.body.strip(), payload.url.strip(), payload.date, user["id"], db.utcnow()),
        )
    return {"id": new_id}


@app.get("/api/threads")
def threads(user=Depends(current_user)):
    with db.connect() as con:
        ts = con.execute("SELECT * FROM threads ORDER BY created_at DESC").fetchall()
        result = []
        for t in ts:
            replies = con.execute("SELECT * FROM replies WHERE thread_id=? ORDER BY created_at", (t["id"],)).fetchall()
            item = dict(t)
            item["replies"] = [dict(r) for r in replies]
            result.append(item)
    return result


@app.post("/api/threads")
def add_thread(payload: ThreadIn, user=Depends(current_user)):
    with db.connect() as con:
        new_id = db.insert_returning_id(con,
            "INSERT INTO threads(title,body,author_id,author_name,created_at) VALUES (?,?,?,?,?)",
            (payload.title.strip(), payload.body.strip(), user["id"], user["name"], db.utcnow()),
        )
    return {"id": new_id}


@app.post("/api/threads/{thread_id}/replies")
def add_reply(thread_id: int, payload: ReplyIn, user=Depends(current_user)):
    with db.connect() as con:
        if not con.execute("SELECT 1 FROM threads WHERE id=?", (thread_id,)).fetchone():
            raise HTTPException(404, "thread not found")
        new_id = db.insert_returning_id(con,
            "INSERT INTO replies(thread_id,body,author_id,author_name,created_at) VALUES (?,?,?,?,?)",
            (thread_id, payload.body.strip(), user["id"], user["name"], db.utcnow()),
        )
    return {"id": new_id}


def load_table(table_id: str) -> dict[str, Any]:
    if table_id not in {tid for tid, _ in db.FIXED_TABLES}:
        raise HTTPException(404, "table not found")
    with db.connect() as con:
        row = con.execute("SELECT state_json FROM tables WHERE id=?", (table_id,)).fetchone()
    if not row:
        raise HTTPException(404, "table not found")
    return json.loads(row["state_json"])


def arm_action_deadline(state: dict[str, Any], seconds: int = 45):
    hand = state.get("hand")
    if state.get("status") == "playing" and hand and hand.get("action_seat") is not None:
        hand["action_deadline"] = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
    elif hand:
        hand["action_deadline"] = None


def save_table(state: dict[str, Any]):
    with db.connect() as con:
        con.execute("UPDATE tables SET state_json=?,name=?,updated_at=? WHERE id=?", (json.dumps(state, ensure_ascii=False), state["name"], db.utcnow(), state["id"]))


table_locks: dict[str, asyncio.Lock] = {}

def get_table_lock(tid: str) -> asyncio.Lock:
    if tid not in table_locks:
        table_locks[tid] = asyncio.Lock()
    return table_locks[tid]


class Hub:
    def __init__(self):
        self.connections: dict[str, list[tuple[WebSocket,int]]] = {}

    async def add(self, table_id: str, ws: WebSocket, user_id: int):
        self.connections.setdefault(table_id, []).append((ws,user_id))

    def remove(self, table_id: str, ws: WebSocket):
        self.connections[table_id] = [(w,u) for w,u in self.connections.get(table_id,[]) if w is not ws]

    async def broadcast(self, table_id: str):
        try:
            state = load_table(table_id)
        except HTTPException:
            return
        dead=[]
        for ws,uid in list(self.connections.get(table_id, [])):
            try:
                await ws.send_json({"type":"state","state":public_state(state,uid),"messages":get_messages(table_id)})
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.remove(table_id,ws)

hub = Hub()


def get_messages(table_id: str):
    with db.connect() as con:
        rows = con.execute("SELECT id,author_name,body,created_at FROM table_messages WHERE table_id=? ORDER BY id DESC LIMIT 50", (table_id,)).fetchall()
    return [dict(r) for r in reversed(rows)]


@app.get("/api/tables")
def tables(user=Depends(current_user)):
    order = {tid: i for i, (tid, _) in enumerate(db.FIXED_TABLES)}
    with db.connect() as con:
        rows = con.execute("SELECT id,name,state_json,updated_at FROM tables").fetchall()
    out=[]
    for r in rows:
        if r["id"] not in order:
            continue
        state=json.loads(r["state_json"])
        out.append({
            "id":r["id"],"name":r["name"],"status":state["status"],
            "players":len(state["seats"]),"max_seats":state["max_seats"],
            "small_blind":state["small_blind"],"big_blind":state["big_blind"],
            "starting_stack":db.TABLE_STARTING_STACK,"starting_stack_bb":150,
            "updated_at":r["updated_at"]
        })
    out.sort(key=lambda x: order[x["id"]])
    return out


@app.post("/api/tables")
async def create_table_disabled(user=Depends(current_user)):
    raise HTTPException(405, "JJ Arena uses two fixed 6-max tables")


@app.get("/api/tables/{table_id}")
def table_state(table_id: str, user=Depends(current_user)):
    return {"state": public_state(load_table(table_id), user["id"]), "messages": get_messages(table_id)}


def seated_table_for_user(user_id: int, exclude: str | None = None) -> str | None:
    with db.connect() as con:
        rows = con.execute("SELECT id,state_json FROM tables").fetchall()
    fixed = {tid for tid, _ in db.FIXED_TABLES}
    for row in rows:
        if row["id"] not in fixed or row["id"] == exclude:
            continue
        state = json.loads(row["state_json"])
        if any(p.get("user_id") == user_id for p in state.get("seats", [])):
            return row["id"]
    return None


@app.post("/api/tables/{table_id}/seat")
async def sit(table_id: str, payload: SeatIn, user=Depends(current_user)):
    other = seated_table_for_user(user["id"], exclude=table_id)
    if other:
        raise HTTPException(400, "別のテーブルに着席中です")
    async with get_table_lock(table_id):
        state=load_table(table_id)
        try:
            seat_player(state,user_id=user["id"],name=user["name"],seat=payload.seat,stack=db.TABLE_STARTING_STACK)
        except ValueError as e:
            raise HTTPException(400,str(e))
        save_table(state)
    await hub.broadcast(table_id)
    return public_state(state,user["id"])


@app.post("/api/tables/{table_id}/leave")
async def leave(table_id: str, user=Depends(current_user)):
    async with get_table_lock(table_id):
        state=load_table(table_id)
        try:
            remove_player(state,user["id"])
        except ValueError as e:
            raise HTTPException(400,str(e))
        save_table(state)
    await hub.broadcast(table_id)
    return {"ok":True}


@app.post("/api/tables/{table_id}/start")
async def start(table_id: str, user=Depends(current_user)):
    async with get_table_lock(table_id):
        state=load_table(table_id)
        if not any(p["user_id"]==user["id"] for p in state["seats"]) and user["role"]!="admin":
            raise HTTPException(403,"sit at the table to start a hand")
        try:
            start_hand(state)
        except ValueError as e:
            raise HTTPException(400,str(e))
        arm_action_deadline(state)
        save_table(state)
    await hub.broadcast(table_id)
    return public_state(state,user["id"])


@app.post("/api/tables/{table_id}/action")
async def action(table_id: str, payload: ActionIn, user=Depends(current_user)):
    async with get_table_lock(table_id):
        state=load_table(table_id)
        try:
            apply_action(state,user["id"],payload.action,payload.amount)
        except ValueError as e:
            raise HTTPException(400,str(e))
        arm_action_deadline(state)
        save_table(state)
    await hub.broadcast(table_id)
    return public_state(state,user["id"])


@app.post("/api/tables/{table_id}/chat")
async def table_chat(table_id: str, payload: ChatIn, user=Depends(current_user)):
    load_table(table_id)
    with db.connect() as con:
        con.execute("INSERT INTO table_messages(table_id,user_id,author_name,body,created_at) VALUES (?,?,?,?,?)",(table_id,user["id"],user["name"],payload.body.strip(),db.utcnow()))
    await hub.broadcast(table_id)
    return {"ok":True}


async def timeout_loop():
    while True:
        await asyncio.sleep(3)
        try:
            ids = [tid for tid, _ in db.FIXED_TABLES]
            for tid in ids:
                changed = False
                async with get_table_lock(tid):
                    try:
                        state = load_table(tid)
                    except HTTPException:
                        continue
                    hand = state.get("hand")
                    deadline = hand.get("action_deadline") if hand else None
                    if state.get("status") == "playing" and deadline and datetime.now(timezone.utc) >= datetime.fromisoformat(deadline):
                        seat = hand.get("action_seat")
                        player = next((p for p in state["seats"] if p["seat"] == seat), None)
                        if player:
                            legal = legal_actions(state, player["user_id"])
                            if legal.get("can_act"):
                                apply_action(state, player["user_id"], "check" if legal.get("can_check") else "fold")
                                if state.get("hand"):
                                    state["hand"]["log"].append(f"{player['name']} timed out")
                                arm_action_deadline(state)
                                save_table(state)
                                changed = True
                if changed:
                    await hub.broadcast(tid)
        except Exception:
            pass


@app.websocket("/ws/tables/{table_id}")
async def table_ws(ws: WebSocket, table_id: str):
    token=ws.query_params.get("token")
    user=db.get_user_by_token(token)
    if not user:
        await ws.close(code=4401)
        return
    try:
        state=load_table(table_id)
    except HTTPException:
        await ws.close(code=4404)
        return
    await ws.accept()
    await hub.add(table_id,ws,user["id"])
    await ws.send_json({"type":"state","state":public_state(state,user["id"]),"messages":get_messages(table_id)})
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.remove(table_id,ws)
    except Exception:
        hub.remove(table_id,ws)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/{path:path}")
def spa(path: str):
    target = STATIC_DIR / path
    if target.is_file():
        return FileResponse(target)
    return FileResponse(STATIC_DIR / "index.html")
