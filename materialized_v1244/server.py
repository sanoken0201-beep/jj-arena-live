from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import uuid
import time
import hashlib
import unicodedata
from pathlib import Path
from typing import Any
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field

import db
from poker_engine import apply_action, blank_table_state, public_state, remove_player, seat_player, start_hand, legal_actions

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(timeout_loop())
    auto_task = asyncio.create_task(auto_deal_loop())
    try:
        yield
    finally:
        task.cancel()
        auto_task.cancel()

app = FastAPI(title="JJ Arena Live", version="1.24.4", lifespan=lifespan, docs_url=None if os.getenv("RENDER") else "/docs", redoc_url=None if os.getenv("RENDER") else "/redoc", openapi_url=None if os.getenv("RENDER") else "/openapi.json")
app.add_middleware(GZipMiddleware, minimum_size=800, compresslevel=5)
db.init_db()
db.ensure_profile_columns()
_removed_duplicate_accounts = db.cleanup_duplicate_kenichiro_users()
if _removed_duplicate_accounts:
    print(f"JJ_ACCOUNT_CLEANUP removed_duplicates={_removed_duplicate_accounts}")
@app.middleware("http")
async def production_security(request: Request, call_next):
    # Same-origin cookie requests are the browser security boundary. SameSite=Lax
    # already blocks most CSRF; an Origin mismatch is rejected when browsers send it.
    if request.method in {"POST","PUT","PATCH","DELETE"}:
        origin=request.headers.get("origin")
        if origin:
            from urllib.parse import urlparse
            if urlparse(origin).netloc.lower() != request.headers.get("host","").lower():
                return Response(status_code=403, content="cross-origin request blocked")
    response=await call_next(request)
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["X-Frame-Options"]="DENY"
    response.headers["Referrer-Policy"]="strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"]="camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    response.headers["Cross-Origin-Opener-Policy"]="same-origin"
    response.headers["Cross-Origin-Resource-Policy"]="same-origin"
    response.headers["Content-Security-Policy"]="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws: wss:; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    if request.url.path.startswith('/api/'):
        response.headers["Cache-Control"]="no-store"
        response.headers["Pragma"]="no-cache"
    elif request.url.path == "/":
        response.headers["Cache-Control"]="no-cache"
    elif request.url.path.startswith('/static/'):
        if request.url.path.endswith(("styles.css","app.js")) and request.url.query == "v=56":
            response.headers["Cache-Control"]="public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"]="public, max-age=86400"
    if os.getenv("RENDER"):
        response.headers["Strict-Transport-Security"]="max-age=31536000; includeSubDomains"
    return response


def bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


SESSION_COOKIE = "__Host-jj_session" if os.getenv("RENDER") else "jj_session"
LEGACY_SESSION_COOKIE = "jj_session"

def request_token(request: Request, authorization: str | None = None) -> str | None:
    return bearer(authorization) or request.cookies.get(SESSION_COOKIE) or request.cookies.get(LEGACY_SESSION_COOKIE)

def current_user(request: Request, authorization: str | None = Header(default=None)):
    user = db.get_user_by_token(request_token(request, authorization))
    if not user:
        raise HTTPException(401, "authentication required")
    if int(user.get("disabled") or 0):
        raise HTTPException(403, "account disabled")
    return user


def admin_user(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "admin only")
    return user


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=bool(os.getenv("RENDER")), samesite="lax", max_age=60*60*24*14, path="/")


_LOGIN_ATTEMPTS: dict[str, list[float]] = {}
_STEPUP_ATTEMPTS: dict[str, list[float]] = {}
TABLE_IDLE_SECONDS=15*60
SERVER_STARTED_AT=time.time()
table_presence: dict[tuple[str,int], float] = {}

def touch_presence(table_id: str, user_id: int) -> None:
    table_presence[(table_id,int(user_id))]=time.time()

def prune_idle_players(state: dict[str, Any], table_id: str, now_ts: float | None = None) -> bool:
    if state.get("status")=="playing":
        return False
    now_ts=now_ts or time.time(); cutoff=now_ts-TABLE_IDLE_SECONDS; before=len(state.get("seats",[]))
    kept=[]
    for p in state.get("seats",[]):
        last=table_presence.get((table_id,int(p.get("user_id",0))),SERVER_STARTED_AT)
        if last >= cutoff:
            kept.append(p)
        else:
            table_presence.pop((table_id,int(p.get("user_id",0))),None)
    state["seats"]=kept
    return len(kept)!=before

def normalize_login_name(value: str) -> str:
    name = unicodedata.normalize("NFKC", value or "").strip().replace(" ", "").replace("\u3000", "")
    chars=[]
    for ch in name:
        code=ord(ch)
        if 0x3041 <= code <= 0x3096:
            ch=chr(code+0x60)
        chars.append(ch)
    name="".join(chars)
    if not re.fullmatch(r"[ァ-ヺー・]{2,20}", name):
        raise HTTPException(400, "名前はカタカナ2〜20文字で入力してください")
    return name


def internal_login_id(name: str) -> str:
    digest=hashlib.sha256(name.encode("utf-8")).hexdigest()[:32]
    return f"pin-{digest}@jj.invalid"


def validate_pin(pin: str) -> str:
    pin=str(pin or "").strip()
    if not re.fullmatch(r"\d{6}", pin):
        raise HTTPException(400, "暗証番号は6桁の数字で入力してください")
    return pin


def _login_key(request: Request, identity: str) -> str:
    host = request.client.host if request.client else "unknown"
    digest = hashlib.sha256(identity.encode()).hexdigest()
    return f"{host}:{digest}"


def _check_login_rate(request: Request, identity: str) -> str:
    key=_login_key(request,identity); now=time.time(); recent=[t for t in _LOGIN_ATTEMPTS.get(key,[]) if now-t<600]
    _LOGIN_ATTEMPTS[key]=recent
    if len(recent)>=5:
        raise HTTPException(429,"暗証番号の試行が多すぎます。10分ほど時間をおいてください")
    return key

def _record_login_failure(key: str) -> None:
    _LOGIN_ATTEMPTS.setdefault(key,[]).append(time.time())


class PinAccess(BaseModel):
    name: str = Field(min_length=1, max_length=30)
    pin: str = Field(min_length=6, max_length=6)


class ChangePinIn(BaseModel):
    current_pin: str = Field(min_length=6, max_length=6)
    new_pin: str = Field(min_length=6, max_length=6)


class ResetPinIn(BaseModel):
    pin: str = Field(min_length=6, max_length=6)


class ProfileIn(BaseModel):
    grade: str = Field(default="", max_length=20)
    faculty: str = Field(default="", max_length=80)
    department: str = Field(default="", max_length=80)
    hometown: str = Field(default="", max_length=80)
    hobbies: str = Field(default="", max_length=250)
    bio: str = Field(default="", max_length=600)
    avatar_data: str = Field(default="", max_length=150000)
    visible: bool = True


class PointEntry(BaseModel):
    name: str
    date: str
    reentries: int = Field(default=0, ge=0, le=50)
    initial: int = Field(gt=0)
    game_type: str = "ring"
    chip_1: int = Field(default=0, ge=0, le=100000)
    chip_5: int = Field(default=0, ge=0, le=100000)
    chip_10: int = Field(default=0, ge=0, le=100000)
    chip_25: int = Field(default=0, ge=0, le=100000)
    chip_100: int = Field(default=0, ge=0, le=100000)
    chip_500: int = Field(default=0, ge=0, le=100000)


# v1.18.6 server-authoritative poker quiz rewards.
class QuizAnswerIn(BaseModel):
    question_id: str = Field(min_length=3, max_length=80)
    answer: int = Field(ge=0, le=100)


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


class TablePresenceIn(BaseModel):
    mode: str = Field(pattern="^(sitout|cancel_sitout|return|rebuy|unready)$")


class SeatIn(BaseModel):
    seat: int = Field(ge=0, le=5)


class ActionIn(BaseModel):
    action: str
    amount: int | None = None
    action_id: str | None = Field(default=None, min_length=8, max_length=80)


class ChatIn(BaseModel):
    body: str = Field(min_length=1, max_length=500)


class MemberUpdateIn(BaseModel):
    disabled: bool | None = None
    ranking_name: str | None = Field(default=None, max_length=30)


class VoidHandIn(BaseModel):
    voided: bool = True
    reason: str = Field(default="", max_length=500)


@app.get("/api/health")
def health():
    with db.connect() as con:
        con.execute("SELECT 1").fetchone()
    return {"ok": True, "service": "JJ Arena Live", "version":"1.24.4", "database":"postgres" if db.IS_POSTGRES else "sqlite"}


@app.post("/api/auth/pin")
def pin_access(payload: PinAccess, response: Response, request: Request):
    name=normalize_login_name(payload.name)
    pin=validate_pin(payload.pin)
    login_id=internal_login_id(name)
    key=_check_login_rate(request,login_id)
    created=False
    with db.connect() as con:
        row=con.execute("SELECT * FROM users WHERE email=?",(login_id,)).fetchone()
        if not row:
            try:
                uid=db.insert_returning_id(con,
                    "INSERT INTO users(name,email,password_hash,role,arena_chips,xp,approved,disabled,ranking_name,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (name,login_id,db.hash_password(pin),"member",0,0,1,0,name,db.utcnow()),
                )
                row=con.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
                created=True
            except Exception:
                row=con.execute("SELECT * FROM users WHERE email=?",(login_id,)).fetchone()
        if not row or not db.verify_password(pin,row["password_hash"]):
            _record_login_failure(key)
            raise HTTPException(401,"名前または暗証番号が違います")
        rowd=dict(row)
        if int(rowd.get("disabled") or 0):
            raise HTTPException(403,"このアカウントは利用停止中です")
        if db.password_needs_rehash(rowd["password_hash"]):
            con.execute("UPDATE users SET password_hash=? WHERE id=?",(db.hash_password(pin),rowd["id"]))
    _LOGIN_ATTEMPTS.pop(key,None)
    token=db.create_session(rowd["id"]); set_session_cookie(response,token)
    return {"user":user_payload(rowd["id"]),"created":created}


@app.post("/api/auth/signup")
def legacy_signup_disabled():
    raise HTTPException(410,"メール登録は廃止しました。名前と6桁PINを利用してください")


@app.post("/api/auth/login")
def legacy_login_disabled():
    raise HTTPException(410,"メールログインは廃止しました。名前と6桁PINを利用してください")


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, authorization: str | None = Header(default=None)):
    token = request_token(request, authorization)
    if token:
        db.delete_session(token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    if LEGACY_SESSION_COOKIE != SESSION_COOKIE:
        response.delete_cookie(LEGACY_SESSION_COOKIE, path="/")
    return {"ok": True}


@app.post("/api/auth/change-pin")
def change_pin(payload: ChangePinIn, request: Request, user=Depends(current_user)):
    current_pin=validate_pin(payload.current_pin); new_pin=validate_pin(payload.new_pin)
    if current_pin==new_pin:
        raise HTTPException(400,"現在と異なる暗証番号を設定してください")
    with db.connect() as con:
        row=con.execute("SELECT password_hash FROM users WHERE id=?",(user["id"],)).fetchone()
        if not row or not db.verify_password(current_pin,row["password_hash"]):
            raise HTTPException(400,"現在の暗証番号が違います")
        con.execute("UPDATE users SET password_hash=? WHERE id=?",(db.hash_password(new_pin),user["id"]))
    db.delete_user_sessions(user["id"],keep_token=request_token(request))
    return {"ok":True}


def user_payload(uid: int):
    with db.connect() as con:
        row = con.execute("SELECT id,name,role,xp,disabled,ranking_name,created_at FROM users WHERE id=?", (uid,)).fetchone()
    return dict(row)


@app.get("/api/me")
def me(user=Depends(current_user)):
    return user_payload(user["id"])


@app.get("/api/admin/members")
def list_members(user=Depends(admin_user)):
    with db.connect() as con:
        rows=con.execute("SELECT id,name,role,disabled,ranking_name,created_at FROM users ORDER BY disabled ASC,name ASC").fetchall()
    return [dict(row) for row in rows]


@app.post("/api/admin/members/{user_id}/reset-pin")
def reset_member_pin(user_id:int,payload:ResetPinIn,user=Depends(admin_user)):
    pin=validate_pin(payload.pin)
    with db.connect() as con:
        row=con.execute("SELECT id FROM users WHERE id=?",(user_id,)).fetchone()
        if not row:
            raise HTTPException(404,"member not found")
        con.execute("UPDATE users SET password_hash=? WHERE id=?",(db.hash_password(pin),user_id))
    db.delete_user_sessions(user_id)
    return {"ok":True}


@app.patch("/api/admin/members/{user_id}")
async def update_member(user_id:int,payload:MemberUpdateIn,user=Depends(admin_user)):
    if user_id==user["id"] and payload.disabled is True:
        raise HTTPException(400,"自分自身を利用停止にはできません")
    with db.connect() as con:
        row=con.execute("SELECT * FROM users WHERE id=?",(user_id,)).fetchone()
        if not row:
            raise HTTPException(404,"member not found")
        if payload.disabled is not None:
            con.execute("UPDATE users SET disabled=? WHERE id=?",(1 if payload.disabled else 0,user_id))
        if payload.ranking_name is not None:
            rn=payload.ranking_name.strip()
            if not rn:
                raise HTTPException(400,"ranking name is required")
            con.execute("UPDATE users SET ranking_name=? WHERE id=?",(rn,user_id))
            con.execute("UPDATE online_hand_results SET ranking_name=? WHERE user_id=?",(rn,user_id))
    should_eject = payload.disabled is True
    if should_eject:
        db.delete_user_sessions(user_id)
        for table_id,_ in db.FIXED_TABLES:
            async with get_table_lock(table_id):
                state=load_table(table_id)
                player=next((p for p in state.get("seats",[]) if p.get("user_id")==user_id),None)
                if not player:
                    continue
                if state.get("status")!="playing" or not player.get("in_hand"):
                    state["seats"]=[p for p in state["seats"] if p.get("user_id")!=user_id]
                else:
                    player["leave_after_hand"]=True
                save_table(state)
            await hub.broadcast(table_id)
    return {"ok":True}


FALL_SEASON_START = "2026-09-01"
FALL_SEASON_END = "2027-04-01"
FALL_SEASON_MONTHS = {"2026-09","2026-10","2026-11","2026-12","2027-01","2027-02","2027-03"}


PROFILE_TEXT_LIMITS = {
    "grade": 20,
    "faculty": 80,
    "department": 80,
    "hometown": 80,
    "hobbies": 250,
    "bio": 600,
}


def _profile_text(value: str | None, key: str) -> str:
    value = (value or "").strip()
    if len(value) > PROFILE_TEXT_LIMITS[key]:
        raise HTTPException(400, f"{key} is too long")
    return value


def _validate_profile_avatar(value: str | None) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    m = re.fullmatch(r"data:image/(webp|jpeg|png);base64,([A-Za-z0-9+/=]+)", value)
    if not m:
        raise HTTPException(400, "アイコン画像の形式が不正です")
    try:
        raw = base64.b64decode(m.group(2), validate=True)
    except Exception:
        raise HTTPException(400, "アイコン画像を読み取れません")
    if len(raw) > 100 * 1024:
        raise HTTPException(400, "アイコン画像が大きすぎます")
    kind = m.group(1)
    valid = (
        (kind == "png" and raw.startswith(b"\x89PNG\r\n\x1a\n"))
        or (kind == "jpeg" and raw.startswith(b"\xff\xd8\xff"))
        or (kind == "webp" and len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP")
    )
    if not valid:
        raise HTTPException(400, "アイコン画像の内容と形式が一致しません")
    return value


def _profile_row(row, *, own: bool = False) -> dict[str, Any]:
    d = dict(row)
    visible = bool(int(d.get("profile_visible") if d.get("profile_visible") is not None else 1))
    base = {
        "id": int(d["id"]),
        "name": d.get("name") or "",
        "ranking_name": d.get("ranking_name") or d.get("name") or "",
        "role": d.get("role") or "member",
        "visible": visible,
    }
    if not (own or visible):
        return base | {"grade":"","faculty":"","department":"","hometown":"","hobbies":"","bio":"","avatar_data":"","updated_at":None}
    return base | {
        "grade": d.get("profile_grade") or "",
        "faculty": d.get("profile_faculty") or "",
        "department": d.get("profile_department") or "",
        "hometown": d.get("profile_hometown") or "",
        "hobbies": d.get("profile_hobbies") or "",
        "bio": d.get("profile_bio") or "",
        "avatar_data": d.get("profile_avatar") or "",
        "updated_at": d.get("profile_updated_at"),
    }


@app.get("/api/profile/me")
def my_profile(user=Depends(current_user)):
    with db.connect() as con:
        row = con.execute("""
            SELECT id,name,role,ranking_name,profile_grade,profile_faculty,profile_department,
                   profile_hometown,profile_hobbies,profile_bio,profile_avatar,profile_visible,profile_updated_at
            FROM users WHERE id=?
        """, (user["id"],)).fetchone()
    if not row:
        raise HTTPException(404, "user not found")
    return _profile_row(row, own=True)


@app.post("/api/profile/me")
def save_my_profile(payload: ProfileIn, user=Depends(current_user)):
    values = {
        "grade": _profile_text(payload.grade, "grade"),
        "faculty": _profile_text(payload.faculty, "faculty"),
        "department": _profile_text(payload.department, "department"),
        "hometown": _profile_text(payload.hometown, "hometown"),
        "hobbies": _profile_text(payload.hobbies, "hobbies"),
        "bio": _profile_text(payload.bio, "bio"),
        "avatar": _validate_profile_avatar(payload.avatar_data),
        "visible": 1 if payload.visible else 0,
        "updated": db.utcnow(),
    }
    with db.connect() as con:
        con.execute("""
            UPDATE users SET profile_grade=?,profile_faculty=?,profile_department=?,profile_hometown=?,
                profile_hobbies=?,profile_bio=?,profile_avatar=?,profile_visible=?,profile_updated_at=? WHERE id=?
        """, (values["grade"],values["faculty"],values["department"],values["hometown"],
              values["hobbies"],values["bio"],values["avatar"],values["visible"],values["updated"],user["id"]))
        row = con.execute("""
            SELECT id,name,role,ranking_name,profile_grade,profile_faculty,profile_department,
                   profile_hometown,profile_hobbies,profile_bio,profile_avatar,profile_visible,profile_updated_at
            FROM users WHERE id=?
        """, (user["id"],)).fetchone()
    return _profile_row(row, own=True)


@app.get("/api/profiles")
def member_profiles(user=Depends(current_user)):
    with db.connect() as con:
        rows = con.execute("""
            SELECT id,name,role,ranking_name,profile_grade,profile_faculty,profile_department,
                   profile_hometown,profile_hobbies,profile_bio,profile_avatar,profile_visible,profile_updated_at
            FROM users WHERE COALESCE(disabled,0)=0
            ORDER BY CASE WHEN role='admin' THEN 0 ELSE 1 END, name ASC, id ASC
        """).fetchall()
    return [_profile_row(row, own=(int(row["id"]) == int(user["id"]))) for row in rows]


@app.get("/api/rankings")
def rankings(month: str | None = None, season: str = "fall", user=Depends(current_user)):
    season = (season or "fall").strip().lower()
    if season not in {"fall", "summer"}:
        raise HTTPException(400, "season must be fall or summer")
    if season == "fall" and month and month not in FALL_SEASON_MONTHS:
        return []
    club_where = "WHERE name != '運営調整'"
    club_params: list[Any] = []
    online_where = "WHERE COALESCE(h.voided,0)=0"
    online_params: list[Any] = []
    if season == "fall":
        club_where += " AND date>=? AND date<?"
        club_params.extend([FALL_SEASON_START, FALL_SEASON_END])
        online_where += " AND h.played_at>=? AND h.played_at<?"
        online_params.extend([FALL_SEASON_START, FALL_SEASON_END])
    else:
        club_where += " AND date<?"
        club_params.append(FALL_SEASON_START)
        online_where += " AND h.played_at<?"
        online_params.append(FALL_SEASON_START)
    if month:
        club_where += " AND substr(date,1,7)=?"
        club_params.append(month)
        online_where += " AND r.month=?"
        online_params.append(month)
    with db.connect() as con:
        club = con.execute(f"""
            SELECT name, SUM(points) AS points, COUNT(*) AS games, MAX(points) AS best,
                   SUM(CASE WHEN points>0 THEN 1 ELSE 0 END) AS wins
            FROM entries {club_where} GROUP BY name
        """, club_params).fetchall()
        online = con.execute(f"""
            SELECT r.ranking_name AS name, SUM(r.points) AS points, COUNT(*) AS games, MAX(r.points) AS best,
                   SUM(CASE WHEN r.points>0 THEN 1 ELSE 0 END) AS wins
            FROM online_hand_results r JOIN online_hands h ON h.hand_id=r.hand_id {online_where} GROUP BY r.ranking_name
        """, online_params).fetchall()
    merged: dict[str, dict[str, Any]] = {}
    for r in club:
        name=r["name"]; merged[name]={"name":name,"club_points":float(r["points"] or 0),"online_points":0.0,"games":int(r["games"] or 0),"online_hands":0,"best":float(r["best"] or 0),"wins":int(r["wins"] or 0)}
    for r in online:
        name=r["name"]; d=merged.setdefault(name,{"name":name,"club_points":0.0,"online_points":0.0,"games":0,"online_hands":0,"best":float(r["best"] or 0),"wins":0})
        d["online_points"]=round(float(r["points"] or 0),2); d["games"]+=int(r["games"] or 0); d["online_hands"]=int(r["games"] or 0); d["best"]=max(float(d["best"] or 0),float(r["best"] or 0)); d["wins"]+=int(r["wins"] or 0)
    rows=[]
    for d in merged.values():
        d["club_points"]=round(d["club_points"],2); d["points"]=round(d["club_points"]+d["online_points"],2); rows.append(d)
    rows.sort(key=lambda x:(-x["points"],-x["best"],x["name"]))
    return [r|{"rank":i+1,"season":season} for i,r in enumerate(rows)]


@app.get("/api/ranking-names")
def ranking_names(user=Depends(current_user)):
    with db.connect() as con:
        entry_rows=con.execute("SELECT DISTINCT name FROM entries WHERE name!='運営調整' AND name IS NOT NULL AND name<>''").fetchall()
        user_rows=con.execute("SELECT DISTINCT ranking_name FROM users WHERE ranking_name IS NOT NULL AND ranking_name<>''").fetchall()
    names={str(r["name"]).strip() for r in entry_rows if r["name"]}
    names.update(str(r["ranking_name"]).strip() for r in user_rows if r["ranking_name"])
    return sorted(names)


@app.get("/api/online/results")
def online_results(limit:int=50,user=Depends(current_user)):
    limit=max(1,min(limit,200))
    with db.connect() as con:
        rows=con.execute("""SELECT r.*,h.gross_pot_bb,h.rake_bb,h.played_at,COALESCE(h.voided,0) voided,h.void_reason FROM online_hand_results r JOIN online_hands h ON h.hand_id=r.hand_id ORDER BY h.played_at DESC,r.id LIMIT ?""",(limit,)).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/online/summary")
def online_summary(user=Depends(current_user)):
    with db.connect() as con:
        row=con.execute("SELECT SUM(CASE WHEN COALESCE(voided,0)=0 THEN 1 ELSE 0 END) hands,SUM(CASE WHEN COALESCE(voided,0)=1 THEN 1 ELSE 0 END) voided_hands,COALESCE(SUM(CASE WHEN COALESCE(voided,0)=0 THEN rake_bb ELSE 0 END),0) rake_bb,COALESCE(SUM(CASE WHEN COALESCE(voided,0)=0 THEN gross_pot_bb ELSE 0 END),0) gross_pot_bb FROM online_hands").fetchone()
    return dict(row)


@app.patch("/api/admin/online-hands/{hand_id}/void")
def void_online_hand(hand_id:str,payload:VoidHandIn,user=Depends(admin_user)):
    with db.connect() as con:
        row=con.execute("SELECT hand_id FROM online_hands WHERE hand_id=?",(hand_id,)).fetchone()
        if not row:
            raise HTTPException(404,"hand not found")
        if payload.voided:
            reason=payload.reason.strip() or "管理者による無効化"
            con.execute("UPDATE online_hands SET voided=1,void_reason=?,voided_at=?,voided_by=? WHERE hand_id=?",(reason,db.utcnow(),user["id"],hand_id))
        else:
            con.execute("UPDATE online_hands SET voided=0,void_reason=NULL,voided_at=NULL,voided_by=NULL WHERE hand_id=?",(hand_id,))
    return {"ok":True,"hand_id":hand_id,"voided":payload.voided}


@app.get("/api/entries")
def entries(limit: int = 40, archive: bool = False, user=Depends(current_user)):
    limit = max(1, min(limit, 200))
    with db.connect() as con:
        if archive:
            rows = con.execute("SELECT * FROM entries ORDER BY date DESC LIMIT ?", (limit,)).fetchall()
        else:
            rows = con.execute("SELECT * FROM entries WHERE date>=? AND date<? ORDER BY date DESC LIMIT ?", (FALL_SEASON_START, FALL_SEASON_END, limit)).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/entries")
def add_entry(payload: PointEntry, user=Depends(admin_user)):
    game_type = payload.game_type.strip().lower()
    if game_type not in {"ring", "tournament"}:
        raise HTTPException(400, "ゲーム種別が不正です")
    entry_day = (payload.date or "")[:10]
    if not (FALL_SEASON_START <= entry_day < FALL_SEASON_END):
        raise HTTPException(400, "後期期間（2026/9/1〜2027/3/31）の日付を入力してください")
    ring_initials = {450: "450 / blind 1-3-3", 900: "900 / blind 2-5-5", 2000: "2000 / blind 5-10-10"}
    tournament_initials = {300: "300 / tournament", 400: "400 / tournament", 500: "500 / tournament", 600: "600 / tournament", 800: "800 / tournament", 1000: "1000 / tournament"}
    initial_map = ring_initials if game_type == "ring" else tournament_initials
    if payload.initial not in initial_map:
        raise HTTPException(400, "初期点はフォームの選択肢から選んでください")
    counts = {1: payload.chip_1, 5: payload.chip_5, 10: payload.chip_10, 25: payload.chip_25, 100: payload.chip_100, 500: payload.chip_500}
    remaining = sum(value * count for value, count in counts.items())
    points = remaining - (payload.reentries + 1) * payload.initial
    eid = "live-" + uuid.uuid4().hex
    game = initial_map[payload.initial]
    with db.connect() as con:
        con.execute(
            "INSERT INTO entries(id,date,name,remaining,reentries,initial,points,game,game_type,source,created_by,created_at,chip_1,chip_5,chip_10,chip_25,chip_100,chip_500) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (eid, payload.date, payload.name.strip(), remaining, payload.reentries, payload.initial, points, game, game_type, "JJ Arena Live", user["id"], db.utcnow(), payload.chip_1, payload.chip_5, payload.chip_10, payload.chip_25, payload.chip_100, payload.chip_500),
        )
    return {"id": eid, "remaining": remaining, "points": points, "chips": {str(k): v for k, v in counts.items()}}


# v1.18.6 server-authoritative poker quiz rewards.
# Every completed question awards exactly 10 official points. The question,
# answer key, completion state, and ledger write all live on the server so a
# browser refresh, double tap, or edited JavaScript cannot award twice.
JJ_QUIZ_REWARD = 10
JJ_QUIZ_POTS = (40, 60, 80, 100, 120, 150, 200)
JJ_QUIZ_BETS = (10, 20, 25, 30, 40, 50, 75)
JJ_QUIZ_OFFSETS = (-10, -7, -5, 5, 7, 10)


def _jj_quiz_schema() -> None:
    uid_type = "BIGINT" if getattr(db, "IS_POSTGRES", False) else "INTEGER"
    ddl = (
        "CREATE TABLE IF NOT EXISTS quiz_attempts("
        "id TEXT PRIMARY KEY,"
        f"user_id {uid_type} NOT NULL REFERENCES users(id),"
        "pot INTEGER NOT NULL,"
        "bet INTEGER NOT NULL,"
        "correct_answer INTEGER NOT NULL,"
        "choices_json TEXT NOT NULL,"
        "answer INTEGER,"
        "created_at TEXT NOT NULL,"
        "answered_at TEXT)"
    )
    with db.connect() as con:
        con.execute(ddl)
        con.execute("CREATE INDEX IF NOT EXISTS idx_quiz_attempts_user_created ON quiz_attempts(user_id,created_at)")


def _jj_quiz_choices(correct: int, seed: int) -> list[int]:
    choices = {int(correct)}
    offsets = list(JJ_QUIZ_OFFSETS)
    start = abs(int(seed)) % len(offsets)
    for i in range(len(offsets)):
        d = offsets[(start + i) % len(offsets)]
        choices.add(max(3, min(60, int(correct) + int(d))))
        if len(choices) >= 4:
            break
    fallback = 3
    while len(choices) < 4:
        if fallback != correct:
            choices.add(fallback)
        fallback += 1
    return sorted(choices)[:4]


def _jj_quiz_payload(row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "pot": int(row["pot"]),
        "bet": int(row["bet"]),
        "choices": [int(v) for v in json.loads(row["choices_json"])],
        "reward": JJ_QUIZ_REWARD,
    }


_jj_quiz_schema()


@app.get("/api/quiz/question")
def quiz_question(user=Depends(current_user)):
    with db.connect() as con:
        existing = con.execute(
            "SELECT id,pot,bet,choices_json FROM quiz_attempts "
            "WHERE user_id=? AND answer IS NULL ORDER BY created_at DESC LIMIT 1",
            (user["id"],),
        ).fetchone()
        if existing:
            return _jj_quiz_payload(existing)

        nonce = uuid.uuid4()
        selector = nonce.int
        pot = JJ_QUIZ_POTS[selector % len(JJ_QUIZ_POTS)]
        bet = JJ_QUIZ_BETS[(selector // len(JJ_QUIZ_POTS)) % len(JJ_QUIZ_BETS)]
        correct = int(bet / (pot + bet + bet) * 100 + 0.5)
        choices = _jj_quiz_choices(correct, selector)
        qid = "q-" + nonce.hex
        created = db.utcnow()
        con.execute(
            "INSERT INTO quiz_attempts(id,user_id,pot,bet,correct_answer,choices_json,answer,created_at,answered_at) "
            "VALUES (?,?,?,?,?,?,NULL,?,NULL)",
            (qid, user["id"], pot, bet, correct, json.dumps(choices, separators=(",", ":")), created),
        )
        row = con.execute(
            "SELECT id,pot,bet,choices_json FROM quiz_attempts WHERE id=? AND user_id=?",
            (qid, user["id"]),
        ).fetchone()
    return _jj_quiz_payload(row)


@app.post("/api/quiz/answer")
def quiz_answer(payload: QuizAnswerIn, user=Depends(current_user)):
    now = db.utcnow()
    with db.connect() as con:
        row = con.execute(
            "SELECT id,user_id,correct_answer,choices_json,answer FROM quiz_attempts "
            "WHERE id=? AND user_id=?",
            (payload.question_id, user["id"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "quiz question not found")

        choices = [int(v) for v in json.loads(row["choices_json"])]
        if int(payload.answer) not in choices:
            raise HTTPException(400, "answer is not one of the choices")

        if row["answer"] is not None:
            return {
                "ok": True,
                "already_answered": True,
                "correct": int(row["answer"]) == int(row["correct_answer"]),
                "correct_answer": int(row["correct_answer"]),
                "awarded": 0,
            }

        cur = con.execute(
            "UPDATE quiz_attempts SET answer=?,answered_at=? "
            "WHERE id=? AND user_id=? AND answer IS NULL",
            (int(payload.answer), now, payload.question_id, user["id"]),
        )
        if int(getattr(cur, "rowcount", 0) or 0) != 1:
            return {
                "ok": True,
                "already_answered": True,
                "correct": False,
                "correct_answer": int(row["correct_answer"]),
                "awarded": 0,
            }

        correct = int(payload.answer) == int(row["correct_answer"])
        txid = "quiz-" + str(payload.question_id)
        reason = "ポーカークイズ回答"
        con.execute(
            "INSERT INTO point_ledger(id,user_id,amount,kind,reason,effective_at,created_by,created_at,reversal_of) "
            "VALUES (?,?,?,?,?,?,?,?,NULL)",
            (txid, user["id"], JJ_QUIZ_REWARD, "quiz_reward", reason, now, user["id"], now),
        )

    return {
        "ok": True,
        "already_answered": False,
        "correct": correct,
        "correct_answer": int(row["correct_answer"]),
        "awarded": JJ_QUIZ_REWARD,
    }


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
    if state.get("status") != "playing":
        state["seats"]=[p for p in state.get("seats",[]) if not p.get("leave_after_hand")]
    db.save_table_state(state)


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
    # JJ only needs two shared practice tables. Do not expose stale/legacy tables.
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
            "players":sum(1 for p in state["seats"] if int(p.get("stack",0))>0 and not bool(p.get("sitting_out")) and not bool(p.get("sit_out_next"))),
            "seated":len(state["seats"]),
            "sitouts":sum(1 for p in state["seats"] if bool(p.get("sitting_out")) or bool(p.get("sit_out_next"))),
            "busted":sum(1 for p in state["seats"] if int(p.get("stack",0))<=0),
            "max_seats":state["max_seats"],
            "small_blind":state["small_blind"],"big_blind":state["big_blind"],
            "starting_stack":db.TABLE_STARTING_STACK,"starting_stack_bb":150,
            "rake_percent":float(state.get("rake_percent",db.RAKE_PERCENT)),"rake_cap_bb":float(state.get("rake_cap",db.TABLE_BB*db.RAKE_CAP_BB))/state["big_blind"],
            "updated_at":r["updated_at"]
        })
    out.sort(key=lambda x: order[x["id"]])
    return out


@app.post("/api/tables")
async def create_table_disabled(user=Depends(current_user)):
    raise HTTPException(405, "JJ Arena uses two fixed 6-max tables")


@app.get("/api/tables/{table_id}")
def table_state(table_id: str, user=Depends(current_user)):
    touch_presence(table_id,user["id"])
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


table_membership_lock = asyncio.Lock()


@app.post("/api/tables/{table_id}/seat")
async def sit(table_id: str, payload: SeatIn, user=Depends(current_user)):
    async with table_membership_lock:
        other = seated_table_for_user(user["id"], exclude=table_id)
        if other:
            raise HTTPException(400, "別のテーブルに着席中です")
        async with get_table_lock(table_id):
            state = load_table(table_id)
            try:
                seat_player(state, user_id=user["id"], name=user["name"], seat=payload.seat, stack=db.TABLE_STARTING_STACK)
            except ValueError as e:
                raise HTTPException(400, str(e))
            save_table(state)
    await hub.broadcast(table_id)
    return public_state(state, user["id"])


@app.post("/api/tables/{table_id}/leave")
async def leave(table_id: str, user=Depends(current_user)):
    async with get_table_lock(table_id):
        state=load_table(table_id)
        try:
            remove_player(state,user["id"])
        except ValueError as e:
            raise HTTPException(400,str(e))
        table_presence.pop((table_id,int(user["id"])),None)
        save_table(state)
    await hub.broadcast(table_id)
    return {"ok":True}


def _jj_table_player_defaults(player: dict[str, Any]) -> None:
    player.setdefault("ready", False)
    player.setdefault("sitting_out", False)
    player.setdefault("sit_out_next", False)


def _jj_table_active_players(state: dict[str, Any]) -> list[dict[str, Any]]:
    for player in state.get("seats", []):
        _jj_table_player_defaults(player)
    return [
        player for player in state.get("seats", [])
        if int(player.get("stack", 0)) > 0 and not bool(player.get("sitting_out"))
    ]


def _jj_table_user(state: dict[str, Any], user_id: int) -> dict[str, Any] | None:
    for player in state.get("seats", []):
        if int(player.get("user_id", -1)) == int(user_id):
            _jj_table_player_defaults(player)
            return player
    return None


@app.post("/api/tables/{table_id}/presence")
async def update_table_presence(table_id: str, payload: TablePresenceIn, user=Depends(current_user)):
    async with get_table_lock(table_id):
        state = load_table(table_id)
        player = _jj_table_user(state, user["id"])
        if not player:
            raise HTTPException(400, "このテーブルに着席していません")
        mode = payload.mode
        if mode == "sitout":
            if state.get("status") == "playing" and player.get("in_hand"):
                player["sit_out_next"] = True
            else:
                player["sitting_out"] = True
                player["sit_out_next"] = False
                player["ready"] = False
        elif mode == "cancel_sitout":
            player["sit_out_next"] = False
        elif mode == "unready":
            if state.get("status") == "playing" or bool(state.get("session_active")):
                raise HTTPException(400, "開始後はREADYを取り消せません")
            player["ready"] = False
        elif mode == "return":
            if int(player.get("stack", 0)) <= 0:
                raise HTTPException(400, "0bbのため復帰するにはRebuyが必要です")
            player["sitting_out"] = False
            player["sit_out_next"] = False
            if not bool(state.get("session_active")):
                player["ready"] = False
        elif mode == "rebuy":
            if state.get("status") == "playing":
                raise HTTPException(400, "ハンド終了後にRebuyしてください")
            if int(player.get("stack", 0)) != 0:
                raise HTTPException(400, "Rebuyは0bbのときだけ利用できます")
            player["stack"] = int(db.TABLE_STARTING_STACK)
            player["sitting_out"] = False
            player["sit_out_next"] = False
            player["ready"] = False
        active = _jj_table_active_players(state)
        if len(active) < 2 and state.get("status") != "playing":
            state["session_active"] = False
            state["next_hand_at_epoch"] = None
        save_table(state)
    await hub.broadcast(table_id)
    return public_state(state, user["id"])


@app.post("/api/tables/{table_id}/start")
async def start(table_id: str, user=Depends(current_user)):
    async with get_table_lock(table_id):
        state = load_table(table_id)
        if state.get("status") == "playing":
            raise HTTPException(400, "ハンド進行中です")
        player = _jj_table_user(state, user["id"])
        if not player:
            raise HTTPException(403, "着席してから参加準備をしてください")
        if int(player.get("stack", 0)) <= 0:
            raise HTTPException(400, "0bbのため参加できません")
        player["sitting_out"] = False
        player["sit_out_next"] = False
        player["ready"] = True
        active = _jj_table_active_players(state)
        if len(active) >= 2 and all(bool(p.get("ready")) for p in active):
            state["session_active"] = True
            state["next_hand_at_epoch"] = None
            try:
                start_hand(state)
            except ValueError as e:
                raise HTTPException(400, str(e))
            arm_action_deadline(state)
        save_table(state)
    await hub.broadcast(table_id)
    return public_state(state, user["id"])


@app.post("/api/tables/{table_id}/action")
async def action(table_id: str, payload: ActionIn, user=Depends(current_user)):
    async with get_table_lock(table_id):
        state = load_table(table_id)
        receipt = str(payload.action_id or "").strip()
        processed = list(state.get("_processed_action_ids") or [])
        if receipt and receipt in processed:
            return public_state(state, user["id"])
        try:
            apply_action(state, user["id"], payload.action, payload.amount)
        except ValueError as e:
            raise HTTPException(400, str(e))
        if receipt:
            state["_processed_action_ids"] = (processed + [receipt])[-120:]
        arm_action_deadline(state)
        save_table(state)
    await hub.broadcast(table_id)
    return public_state(state, user["id"])


@app.post("/api/tables/{table_id}/rebuy")
async def rebuy(table_id: str, user=Depends(current_user)):
    async with get_table_lock(table_id):
        state=load_table(table_id)
        if state.get("status")=="playing":
            raise HTTPException(400,"ハンド中はリバイできません")
        player=next((p for p in state.get("seats",[]) if p.get("user_id")==user["id"]),None)
        if not player:
            raise HTTPException(400,"着席していません")
        if int(player.get("stack",0))>0:
            raise HTTPException(400,"0bbのときだけ150bbへリバイできます")
        player.update({"stack":db.TABLE_STARTING_STACK,"in_hand":False,"folded":False,"all_in":False,"round_bet":0,"contributed":0,"cards":[]})
        touch_presence(table_id,user["id"])
        save_table(state)
    await hub.broadcast(table_id)
    return public_state(state,user["id"])


@app.post("/api/tables/{table_id}/chat")
async def table_chat(table_id: str, payload: ChatIn, user=Depends(current_user)):
    load_table(table_id)
    touch_presence(table_id,user["id"])
    with db.connect() as con:
        con.execute("INSERT INTO table_messages(table_id,user_id,author_name,body,created_at) VALUES (?,?,?,?,?)",(table_id,user["id"],user["name"],payload.body.strip(),db.utcnow()))
    await hub.broadcast(table_id)
    return {"ok":True}


async def auto_deal_loop():
    """Continue a live table automatically after the result display delay."""
    while True:
        await asyncio.sleep(0.5)
        for table_id, _ in db.FIXED_TABLES:
            changed = False
            async with get_table_lock(table_id):
                try:
                    state = load_table(table_id)
                except HTTPException:
                    continue
                if state.get("status") != "waiting" or not bool(state.get("session_active")):
                    continue
                active = _jj_table_active_players(state)
                if len(active) < 2:
                    state["session_active"] = False
                    state["next_hand_at_epoch"] = None
                    for player in state.get("seats", []):
                        player["ready"] = False
                    save_table(state)
                    changed = True
                else:
                    due = state.get("next_hand_at_epoch")
                    if due is None:
                        state["next_hand_at_epoch"] = time.time() + 1.6
                        save_table(state)
                        changed = True
                    elif time.time() >= float(due):
                        try:
                            start_hand(state)
                        except ValueError:
                            state["session_active"] = False
                            state["next_hand_at_epoch"] = None
                        else:
                            arm_action_deadline(state)
                        save_table(state)
                        changed = True
            if changed:
                await hub.broadcast(table_id)


async def timeout_loop():
    while True:
        await asyncio.sleep(3)
        try:
            with db.connect() as con:
                ids = [tid for tid, _ in db.FIXED_TABLES]
            for tid in ids:
                changed = False
                async with get_table_lock(tid):
                    try:
                        state = load_table(tid)
                    except HTTPException:
                        continue
                    if prune_idle_players(state,tid):
                        save_table(state); changed=True
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
                                    state["hand"]["log"].append(f"{player['name']} timed out · sit out next")
                                if state.get("status") == "playing":
                                    player["sit_out_next"] = True
                                else:
                                    player["sitting_out"] = True
                                    player["sit_out_next"] = False
                                    player["ready"] = False
                                    active_after_timeout = _jj_table_active_players(state)
                                    if len(active_after_timeout) < 2:
                                        state["session_active"] = False
                                        state["next_hand_at_epoch"] = None
                                arm_action_deadline(state)
                                save_table(state)
                                changed = True
                if changed:
                    await hub.broadcast(tid)
        except Exception:
            # The game server should stay alive even if one timeout scan fails.
            pass

# v1.16.2 server-selected seat join.
# Primary seating no longer depends on a tiny seat marker in the table DOM.
# The server chooses and reserves one real empty seat while holding the same
# cross-table membership lock used by explicit seat selection.
@app.post("/api/tables/{table_id}/join")
async def join_table(table_id: str, user=Depends(current_user)):
    async with table_membership_lock:
        async with get_table_lock(table_id):
            state = load_table(table_id)
            existing = _jj_table_user(state, user["id"])
            if existing:
                return public_state(state, user["id"])

        other = seated_table_for_user(user["id"], exclude=table_id)
        if other:
            raise HTTPException(400, "別のテーブルに着席中です")

        async with get_table_lock(table_id):
            state = load_table(table_id)
            existing = _jj_table_user(state, user["id"])
            if existing:
                return public_state(state, user["id"])
            occupied = {int(p.get("seat", -1)) for p in state.get("seats", [])}
            free = [seat for seat in range(int(state.get("max_seats", 6))) if seat not in occupied]
            if not free:
                raise HTTPException(409, "このテーブルは満席です")

            button = int(state.get("button_seat", -1))
            free.sort(key=lambda seat: ((seat - button) % int(state.get("max_seats", 6))))
            chosen = free[0]
            live_session = bool(state.get("session_active")) or state.get("status") == "playing"
            try:
                seat_player(
                    state,
                    user_id=user["id"],
                    name=user["name"],
                    seat=chosen,
                    stack=db.TABLE_STARTING_STACK,
                )
            except ValueError as e:
                raise HTTPException(400, str(e))

            player = _jj_table_user(state, user["id"])
            if player and live_session:
                player["sitting_out"] = False
                player["sit_out_next"] = False
                player["ready"] = False
                player["in_hand"] = False
                player["folded"] = False
                player["all_in"] = False
                player["round_bet"] = 0
                player["contributed"] = 0
                player["cards"] = []
            save_table(state)

    await hub.broadcast(table_id)
    return public_state(state, user["id"])


@app.websocket("/ws/tables/{table_id}")
async def table_ws(ws: WebSocket, table_id: str):
    await ws.accept()

    # Browser WebSockets send Origin. Reject an explicit cross-origin handshake
    # before reading any authenticated table state. Non-browser clients without
    # Origin are still permitted for health/testing compatibility.
    origin = str(ws.headers.get("origin") or "").rstrip("/")
    host = str(ws.headers.get("host") or "").strip()
    if origin and host and origin not in {f"https://{host}", f"http://{host}"}:
        await ws.close(code=4403)
        return

    token = request_token(ws)
    user = db.get_user_by_token(token)
    if not user:
        await ws.close(code=4401)
        return
    if int(user.get("disabled") or 0):
        await ws.close(code=4403)
        return
    try:
        state = load_table(table_id)
    except HTTPException:
        await ws.close(code=4404)
        return

    await hub.add(table_id, ws, user["id"])
    try:
        await ws.send_json({"type":"state","state":public_state(state,user["id"]),"messages":get_messages(table_id)})
        while True:
            message = await ws.receive_text()
            if message == "ping":
                continue
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        import resilience as _jj_resilience; _jj_resilience.record_error(db, "websocket", f"{type(exc).__name__}: {exc}", path=table_id)
    finally:
        hub.remove(table_id, ws)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.head("/")
def head_index():
    return Response(status_code=200)

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/{path:path}")
def spa(path: str):
    target = STATIC_DIR / path
    if target.is_file():
        return FileResponse(target)
    return FileResponse(STATIC_DIR / "index.html")


# v1.16 table-state invariant repair. Persistent tables survive deploys, so old
# transient flags must be normalized rather than trusted indefinitely.
_jj_v16_base_load_table = load_table


def _jj_v16_repair_table_state(state: dict[str, Any]) -> bool:
    changed = False
    if "session_active" not in state:
        state["session_active"] = False; changed = True
    if "next_hand_at_epoch" not in state:
        state["next_hand_at_epoch"] = None; changed = True
    playing = state.get("status") == "playing"
    for player in state.get("seats", []):
        for key, default in (("ready", False), ("sitting_out", False), ("sit_out_next", False)):
            if key not in player:
                player[key] = default; changed = True
        if player.get("sitting_out"):
            if player.get("ready"):
                player["ready"] = False; changed = True
            if player.get("sit_out_next"):
                player["sit_out_next"] = False; changed = True
        if int(player.get("stack", 0)) <= 0:
            if player.get("ready"):
                player["ready"] = False; changed = True
            if player.get("sit_out_next"):
                player["sit_out_next"] = False; changed = True
        if not playing and player.get("sit_out_next"):
            player["sit_out_next"] = False
            player["sitting_out"] = True
            player["ready"] = False
            changed = True
    eligible = [p for p in state.get("seats", []) if int(p.get("stack",0)) > 0 and not bool(p.get("sitting_out"))]
    if playing:
        if not bool(state.get("session_active")):
            state["session_active"] = True; changed = True
        if state.get("next_hand_at_epoch") is not None:
            state["next_hand_at_epoch"] = None; changed = True
    else:
        if bool(state.get("session_active")) and len(eligible) < 2:
            state["session_active"] = False
            state["next_hand_at_epoch"] = None
            changed = True
        elif not bool(state.get("session_active")) and state.get("next_hand_at_epoch") is not None:
            state["next_hand_at_epoch"] = None; changed = True
    return changed


def load_table(table_id: str) -> dict[str, Any]:
    state = _jj_v16_base_load_table(table_id)
    if _jj_v16_repair_table_state(state):
        save_table(state)
    return state


def _jj_v16_repair_all_tables() -> None:
    for table_id, _ in db.FIXED_TABLES:
        try:
            load_table(table_id)
        except Exception:
            pass


_jj_v16_repair_all_tables()


# v1.23.0 staged forced-runout scheduler.
# Reuse the existing lifecycle task instead of creating another lifespan hook.
# The legacy auto-deal loop continues untouched as a child task; this wrapper
# only advances due all-in runouts one street at a time and broadcasts each frame.
from poker_engine import advance_forced_runout

_jj_v123_base_auto_deal_loop = auto_deal_loop


async def auto_deal_loop():
    base_task = asyncio.create_task(_jj_v123_base_auto_deal_loop())
    try:
        while True:
            await asyncio.sleep(0.18)
            now = time.time()
            for table_id in FIXED_TABLE_IDS:
                try:
                    async with table_locks[table_id]:
                        state = load_table(table_id)
                        hand = state.get("hand") or {}
                        due = float(hand.get("runout_due_at_epoch") or 0)
                        if (
                            state.get("status") == "playing"
                            and hand.get("forced_runout")
                            and due
                            and due <= now
                            and advance_forced_runout(state)
                        ):
                            arm_action_deadline(state)
                            save_table(state)
                            await broadcast_table(table_id)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    # v1.23.0 forced-runout operational logging. A single table
                    # must not stop the lifecycle, but a stuck staged runout must
                    # remain diagnosable from the existing operations error log.
                    import resilience as _jj_v123_resilience
                    _jj_v123_resilience.record_error(
                        db,
                        "forced_runout",
                        f"{type(exc).__name__}: {exc}",
                        path=table_id,
                    )
                    continue
    finally:
        base_task.cancel()
        await asyncio.gather(base_task, return_exceptions=True)

# v1.23.0 reconstructed-server scheduler compatibility final.
# The verified server exposes fixed tables through db.FIXED_TABLES, locking via
# get_table_lock(), and broadcast via hub.broadcast(). Replace the earlier
# provisional scheduler wrapper with one that uses those actual contracts.
_jj_v123_server_base_auto_deal_loop = _jj_v123_base_auto_deal_loop


async def auto_deal_loop():
    base_task = asyncio.create_task(_jj_v123_server_base_auto_deal_loop())
    try:
        while True:
            await asyncio.sleep(0.18)
            now = time.time()
            for table_id, _table_name in db.FIXED_TABLES:
                changed = False
                try:
                    async with get_table_lock(table_id):
                        state = load_table(table_id)
                        hand = state.get("hand") or {}
                        due = float(hand.get("runout_due_at_epoch") or 0)
                        if (
                            state.get("status") == "playing"
                            and hand.get("forced_runout")
                            and due
                            and due <= now
                            and advance_forced_runout(state)
                        ):
                            # Forced runout frames have no player decision, so do
                            # not arm an action timeout here. Normal next-hand
                            # dealing remains owned by the established base loop.
                            save_table(state)
                            changed = True
                    if changed:
                        await hub.broadcast(table_id)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    import resilience as _jj_v123_resilience
                    _jj_v123_resilience.record_error(
                        db,
                        "forced_runout",
                        f"{type(exc).__name__}: {exc}",
                        path=table_id,
                    )
    finally:
        base_task.cancel()
        await asyncio.gather(base_task, return_exceptions=True)

# v1.24.4 analysis focus-hand endpoint
# Read-only bridge from an observed aggregate tendency to the exact recent hands
# that formed that metric's denominator. It does not score decisions or alter
# poker state, ranking, points, or stored analytics.
from datetime import datetime as _jj_v1244_datetime, timedelta as _jj_v1244_timedelta, timezone as _jj_v1244_timezone

_JJ_V1244_FOCUS_SQL = {
    "vpip_pfr_gap": "p.vpip=1 AND p.pfr=0",
    "fold_to_3bet": "p.faced_three_bet=1",
    "three_bet": "p.three_bet_opp=1",
    "cbet": "p.cbet_opp=1",
    "position_vpip": "p.position IN ('UTG','UTG+1','MP','LJ','HJ','CO','BTN','BTN/SB')",
    "timeout": "p.timeout_count>0",
}


def _jj_v1244_focus_start(range_name: str):
    days = {"7d": 7, "30d": 30, "90d": 90}.get(str(range_name or "all"))
    if not days:
        return None
    return (_jj_v1244_datetime.now(_jj_v1244_timezone.utc) - _jj_v1244_timedelta(days=days)).isoformat()


@app.get("/api/analysis/focus-hands")
def jj_v1244_analysis_focus_hands(metric: str, range: str = "all", limit: int = 12, user=Depends(current_user)):
    condition = _JJ_V1244_FOCUS_SQL.get(str(metric or ""))
    if condition is None:
        raise HTTPException(status_code=400, detail="未対応の分析指標です")
    limit = max(1, min(24, int(limit or 12)))
    where = ["p.user_id=?", "h.completed_at IS NOT NULL", "COALESCE(h.partial_capture,0)=0", condition]
    params = [int(user["id"])]
    start = _jj_v1244_focus_start(range)
    if start:
        where.append("h.completed_at>=?")
        params.append(start)
    params.append(limit)
    sql = f"""
      SELECT h.hand_id,h.table_id,h.table_name,h.hand_no,h.completed_at,h.reached_street,h.showdown,
             p.position,p.net_bb,p.starting_stack_bb,p.effective_stack_bb,p.vpip,p.pfr,
             p.three_bet_opp,p.three_bet,p.faced_three_bet,p.folded_to_three_bet,
             p.cbet_opp,p.cbet,p.timeout_count
      FROM jj_hand_players p
      JOIN jj_hand_history h ON h.hand_id=p.hand_id
      WHERE {' AND '.join(where)}
      ORDER BY h.completed_at DESC
      LIMIT ?
    """
    with db.connect() as con:
        rows = con.execute(sql, tuple(params)).fetchall()
    out = []
    for row in rows:
        r = dict(row)
        out.append({
            "hand_id": str(r.get("hand_id") or ""),
            "table_id": str(r.get("table_id") or ""),
            "table_name": str(r.get("table_name") or ""),
            "hand_no": int(r.get("hand_no") or 0),
            "completed_at": r.get("completed_at"),
            "reached_street": str(r.get("reached_street") or "preflop"),
            "showdown": bool(r.get("showdown")),
            "position": str(r.get("position") or "—"),
            "net_bb": float(r.get("net_bb") or 0),
            "starting_stack_bb": float(r.get("starting_stack_bb") or 0),
            "effective_stack_bb": float(r.get("effective_stack_bb") or 0),
            "context": {
                "vpip": bool(r.get("vpip")), "pfr": bool(r.get("pfr")),
                "three_bet_opp": bool(r.get("three_bet_opp")), "three_bet": bool(r.get("three_bet")),
                "faced_three_bet": bool(r.get("faced_three_bet")), "folded_to_three_bet": bool(r.get("folded_to_three_bet")),
                "cbet_opp": bool(r.get("cbet_opp")), "cbet": bool(r.get("cbet")),
                "timeout_count": int(r.get("timeout_count") or 0),
            },
        })
    return {"metric": metric, "range": range, "hands": out, "count": len(out)}

