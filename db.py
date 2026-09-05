from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("JJ_DB_PATH", BASE_DIR / "jj_arena.db"))
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
IS_POSTGRES = bool(DATABASE_URL)

FIXED_TABLES = (("jj-table-a", "JJ Table A"), ("jj-table-b", "JJ Table B"))
TABLE_MAX_SEATS = 6
TABLE_SB = 50
TABLE_BB = 100
TABLE_STARTING_STACK = 15_000  # 150bb when BB=100

# Aggregated from JJ 2026 Summer Season. New activity is stored as normal entries.
SUMMER = {'Luke': {'2026-06': 378, '2026-07': 2242}, 'Mahen': {'2026-06': 1702, '2026-07': -465}, 'MeiLi': {'2026-06': -952, '2026-07': 2618}, 'Pekka': {'2026-06': -858, '2026-07': 855}, 'Tuomas': {'2026-06': -450, '2026-07': -900}, 'アツシ': {'2026-06': -451}, 'アユム': {'2026-06': 1317, '2026-07': 39, '2026-08': 2}, 'イズミ': {'2026-06': -671, '2026-07': -164, '2026-08': 1115}, 'エイデン': {'2026-06': -4424, '2026-07': -324}, 'カイジ': {'2026-06': -596}, 'カズキ': {'2026-06': -300}, 'ガク': {'2026-06': 55, '2026-07': 59, '2026-08': 2096}, 'キミ': {'2026-06': -639, '2026-07': 364}, 'ケイセイ': {'2026-06': -467}, 'ケイタロウ': {'2026-07': 1015}, 'ケンイチロウ': {'2026-04': 0, '2026-06': 689, '2026-07': -84, '2026-08': -2323}, 'ゲンヤ': {'2026-06': -168}, 'コウタロウ': {'2026-06': -2698}, 'コウヨウ': {'2026-06': 361}, 'シオン': {'2026-07': -809, '2026-08': 186}, 'ショウタ': {'2026-06': -387}, 'ジンギョム': {'2026-06': 717, '2026-07': -937}, 'ソラミ': {'2026-06': -866, '2026-07': -803, '2026-08': -449}, 'タイセイ': {'2026-06': 746, '2026-07': -1324}, 'タクマ': {'2026-06': 1529}, 'テルアキ': {'2026-06': -718}, 'トミー': {'2026-06': -898, '2026-07': -2018}, 'トモマサ': {'2026-06': 3800, '2026-07': -519}, 'トモリ': {'2026-06': 2427, '2026-07': 216, '2026-08': -2674}, 'ハルキ': {'2026-06': 277, '2026-07': 906, '2026-08': 2169}, 'バサ': {'2026-06': -955}, 'ムツミ': {'2026-06': 645, '2026-07': 26}, 'ユウイチロウ': {'2026-06': 428, '2026-07': 289}, 'ユウマ': {'2026-06': 1178}, 'ヨシハル': {'2026-06': 1025, '2026-07': 4532, '2026-08': 1126}, 'リュウセイ': {'2026-06': 3190, '2026-07': 1305, '2026-08': 147}, 'レオン': {'2026-06': -1268}, 'ワディ': {'2026-06': 741, '2026-07': 1076, '2026-08': -239}, '運営調整': {'2026-07': -10634}}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class PgConnection:
    def __init__(self, con): self._con = con
    @staticmethod
    def _sql(sql: str) -> str:
        return sql.replace("?", "%s").replace("INSERT OR IGNORE INTO", "INSERT INTO")
    def execute(self, sql: str, params=()):
        q = self._sql(sql)
        if "INSERT OR IGNORE INTO" in sql: q += " ON CONFLICT DO NOTHING"
        cur = self._con.cursor(); cur.execute(q, params); return cur
    def executescript(self, script: str):
        cur = self._con.cursor()
        for stmt in [s.strip() for s in script.split(";") if s.strip()]: cur.execute(stmt)
        return cur


@contextmanager
def connect():
    if IS_POSTGRES:
        import psycopg
        from psycopg.rows import dict_row
        url = DATABASE_URL
        if "render.com" in url and "sslmode=" not in url and "internal" not in url:
            url += ("&" if "?" in url else "?") + "sslmode=require"
        raw = psycopg.connect(url, row_factory=dict_row); con = PgConnection(raw)
        try:
            yield con; raw.commit()
        except Exception:
            raw.rollback(); raise
        finally: raw.close()
    else:
        raw = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False); raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA foreign_keys=ON"); raw.execute("PRAGMA journal_mode=WAL")
        try: yield raw; raw.commit()
        finally: raw.close()


def insert_returning_id(con, sql: str, params=()) -> int:
    if IS_POSTGRES:
        return int(con.execute(sql.rstrip().rstrip(";") + " RETURNING id", params).fetchone()["id"])
    return int(con.execute(sql, params).lastrowid)


def hash_password(password: str, salt: bytes | None = None) -> str:
    if len(password) < 6: raise ValueError("password must be at least 6 characters")
    salt = salt or secrets.token_bytes(16)
    rounds = 210_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds)
    return f"pbkdf2_sha256${rounds}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded: return False
    try:
        if not encoded.startswith("pbkdf2_sha256$"):
            salt_hex, digest_hex = encoded.split("$", 1)
            got = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 150_000).hex()
            return secrets.compare_digest(got, digest_hex)
        _, rounds, salt_hex, digest_hex = encoded.split("$", 3)
        got = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds)).hex()
        return secrets.compare_digest(got, digest_hex)
    except Exception: return False


def _pg_columns(con, table: str) -> set[str]:
    if not IS_POSTGRES: return set()
    rows = con.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=?", (table,)).fetchall()
    return {r["column_name"] for r in rows}


def _migrate_legacy_beta(con):
    if not IS_POSTGRES: return
    cols = _pg_columns(con, "users")
    if cols:
        for col, typ in (("password_hash","TEXT"),("arena_chips","INTEGER NOT NULL DEFAULT 0"),("created_at","TEXT")):
            con.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {typ}")
        cols = _pg_columns(con, "users")
        if "ph" in cols: con.execute("UPDATE users SET password_hash=ph WHERE password_hash IS NULL")
        if "chips" in cols: con.execute("UPDATE users SET arena_chips=chips WHERE arena_chips=0")
        con.execute("UPDATE users SET created_at=? WHERE created_at IS NULL", (utcnow(),))
    cols = _pg_columns(con, "sessions")
    if cols:
        con.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS expires_at TEXT")
        con.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS created_at TEXT")
        cols = _pg_columns(con, "sessions")
        if "expires" in cols: con.execute("UPDATE sessions SET expires_at=expires WHERE expires_at IS NULL")
        con.execute("UPDATE sessions SET created_at=? WHERE created_at IS NULL", (utcnow(),))
    for table in ("schedules", "announcements"):
        if _pg_columns(con, table):
            con.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS created_by BIGINT")
            con.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS created_at TEXT")
            con.execute(f"UPDATE {table} SET created_at=? WHERE created_at IS NULL", (utcnow(),))
    cols = _pg_columns(con, "threads")
    if cols:
        con.execute("ALTER TABLE threads ADD COLUMN IF NOT EXISTS author_id BIGINT")
        con.execute("ALTER TABLE threads ADD COLUMN IF NOT EXISTS author_name TEXT")
        con.execute("ALTER TABLE threads ADD COLUMN IF NOT EXISTS created_at TEXT")
        if "author" in _pg_columns(con, "threads"): con.execute("UPDATE threads SET author_name=author WHERE author_name IS NULL")
        con.execute("UPDATE threads SET author_name='JJ Arena',created_at=? WHERE created_at IS NULL", (utcnow(),))
    cols = _pg_columns(con, "replies")
    if cols:
        con.execute("ALTER TABLE replies ADD COLUMN IF NOT EXISTS author_id BIGINT")
        con.execute("ALTER TABLE replies ADD COLUMN IF NOT EXISTS author_name TEXT")
        con.execute("ALTER TABLE replies ADD COLUMN IF NOT EXISTS created_at TEXT")
        if "author" in _pg_columns(con, "replies"): con.execute("UPDATE replies SET author_name=author WHERE author_name IS NULL")
        con.execute("UPDATE replies SET author_name='Member',created_at=? WHERE created_at IS NULL", (utcnow(),))


def init_db():
    idcol = "BIGSERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    schema = f"""
    CREATE TABLE IF NOT EXISTS users (id {idcol}, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, password_hash TEXT, role TEXT NOT NULL DEFAULT 'member', arena_chips INTEGER NOT NULL DEFAULT 0, xp INTEGER NOT NULL DEFAULT 0, created_at TEXT);
    CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires_at TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS entries (id TEXT PRIMARY KEY, date TEXT NOT NULL, name TEXT NOT NULL, remaining INTEGER NOT NULL, reentries INTEGER NOT NULL, initial INTEGER NOT NULL, points INTEGER NOT NULL, game TEXT, game_type TEXT, source TEXT, created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_entries_name_date ON entries(name,date);
    CREATE TABLE IF NOT EXISTS schedules (id {idcol}, date TEXT NOT NULL, time TEXT NOT NULL, room TEXT NOT NULL, title TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', created_by INTEGER REFERENCES users(id), created_at TEXT);
    CREATE TABLE IF NOT EXISTS announcements (id {idcol}, kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, url TEXT NOT NULL DEFAULT '', date TEXT NOT NULL, created_by INTEGER REFERENCES users(id), created_at TEXT);
    CREATE TABLE IF NOT EXISTS threads (id {idcol}, title TEXT NOT NULL, body TEXT NOT NULL, author_id INTEGER REFERENCES users(id), author_name TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS replies (id {idcol}, thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE, body TEXT NOT NULL, author_id INTEGER REFERENCES users(id), author_name TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS tables (id TEXT PRIMARY KEY, name TEXT NOT NULL, owner_id INTEGER REFERENCES users(id), state_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS table_messages (id {idcol}, table_id TEXT NOT NULL REFERENCES tables(id) ON DELETE CASCADE, user_id INTEGER REFERENCES users(id), author_name TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL);
    """
    with connect() as con:
        _migrate_legacy_beta(con); con.executescript(schema)
        if IS_POSTGRES and _pg_columns(con, "historical") and con.execute("SELECT COUNT(*) c FROM entries").fetchone()["c"] == 0:
            for r in con.execute("SELECT name,month,points FROM historical").fetchall():
                con.execute("INSERT OR IGNORE INTO entries(id,date,name,remaining,reentries,initial,points,game,game_type,source,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (f"legacy-{r['name']}-{r['month']}", r['month']+"-01", r['name'], 0, 0, 1, int(r['points']), "Summer aggregate", "ring", "JJ 2026 Summer Season", utcnow()))
    seed_if_needed()


def _ensure_fixed_tables(con):
    from poker_engine import blank_table_state
    for tid, name in FIXED_TABLES:
        row = con.execute("SELECT state_json FROM tables WHERE id=?", (tid,)).fetchone()
        if row:
            state = json.loads(row["state_json"])
            state.update({"name":name,"max_seats":TABLE_MAX_SEATS,"small_blind":TABLE_SB,"big_blind":TABLE_BB,"min_buyin":TABLE_STARTING_STACK,"max_buyin":TABLE_STARTING_STACK})
        else:
            state = blank_table_state(table_id=tid,name=name,max_seats=TABLE_MAX_SEATS,small_blind=TABLE_SB,big_blind=TABLE_BB,min_buyin=TABLE_STARTING_STACK,max_buyin=TABLE_STARTING_STACK)
            con.execute("INSERT INTO tables(id,name,owner_id,state_json,created_at,updated_at) VALUES (?,?,?,?,?,?)",(tid,name,None,json.dumps(state,ensure_ascii=False),utcnow(),utcnow()))
            continue
        con.execute("UPDATE tables SET name=?,state_json=?,updated_at=? WHERE id=?",(name,json.dumps(state,ensure_ascii=False),utcnow(),tid))


def seed_if_needed():
    with connect() as con:
        if con.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] == 0:
            admin_name=os.getenv("JJ_ADMIN_NAME","ケンイチロウ"); admin_email=os.getenv("JJ_ADMIN_EMAIL","admin@jj.local"); admin_password=os.getenv("JJ_ADMIN_PASSWORD") or "admin2026"
            con.execute("INSERT INTO users(name,email,password_hash,role,arena_chips,xp,created_at) VALUES (?,?,?,?,?,?,?)",(admin_name,admin_email,hash_password(admin_password),"admin",0,0,utcnow()))
            if os.getenv("JJ_ENABLE_DEMO_MEMBER", "1" if not IS_POSTGRES else "0") == "1":
                con.execute("INSERT INTO users(name,email,password_hash,role,arena_chips,xp,created_at) VALUES (?,?,?,?,?,?,?)",("ヨシハル","member@jj.local",hash_password("jj2026"),"member",0,0,utcnow()))
        if con.execute("SELECT COUNT(*) c FROM entries").fetchone()["c"] == 0:
            for name, months in SUMMER.items():
                for month, points in months.items():
                    con.execute("INSERT OR IGNORE INTO entries(id,date,name,remaining,reentries,initial,points,game,game_type,source,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",(f"summer-{name}-{month}",month+"-01",name,0,0,1,points,"Summer aggregate","ring","JJ 2026 Summer Season",utcnow()))
        if con.execute("SELECT COUNT(*) c FROM announcements").fetchone()["c"] == 0:
            con.execute("INSERT INTO announcements(kind,title,body,url,date,created_at) VALUES (?,?,?,?,?,?)",("club","JJ Arena v1","共有運用に向けた公開版です。ランキング・予定・戦略議論・固定2卓の6-max NLHを利用できます。","","2026-09-06",utcnow()))
        if con.execute("SELECT COUNT(*) c FROM threads").fetchone()["c"] == 0:
            con.execute("INSERT INTO threads(title,body,author_name,created_at) VALUES (?,?,?,?)",("ハンドレビュー / 戦略議論","気になったハンド、ベットサイズ、ICM、エクスプロイトなどを投稿できます。","JJ Arena",utcnow()))
        _ensure_fixed_tables(con)


def create_session(user_id:int)->str:
    token=secrets.token_urlsafe(32); expires=datetime.now(timezone.utc)+timedelta(days=30)
    with connect() as con:
        con.execute("DELETE FROM sessions WHERE user_id=? OR expires_at < ?",(user_id,utcnow()))
        con.execute("INSERT INTO sessions(token,user_id,expires_at,created_at) VALUES (?,?,?,?)",(token,user_id,expires.isoformat(),utcnow()))
    return token


def delete_session(token:str|None)->None:
    if token:
        with connect() as con: con.execute("DELETE FROM sessions WHERE token=?",(token,))


def get_user_by_token(token:str|None)->dict[str,Any]|None:
    if not token: return None
    with connect() as con:
        row=con.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires_at > ?",(token,utcnow())).fetchone()
    return dict(row) if row else None
