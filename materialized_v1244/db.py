from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
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
ONLINE_POINTS_PER_BB = 3  # 1 online bb = 3 ranking points
RAKE_PERCENT = 0.10
RAKE_CAP_BB = 5

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
    # Length policy is enforced at signup/change-password. Keep hashing compatible
    # with legacy beta accounts that may have shorter passwords.
    salt = salt or secrets.token_bytes(16)
    rounds = int(os.getenv("JJ_PBKDF2_ROUNDS", "600000"))
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


PBKDF2_ROUNDS = int(os.getenv("JJ_PBKDF2_ROUNDS", "600000"))

def password_needs_rehash(encoded: str | None) -> bool:
    if not encoded or not encoded.startswith("pbkdf2_sha256$"):
        return True
    try:
        _, rounds, _, _ = encoded.split("$", 3)
        return int(rounds) < PBKDF2_ROUNDS
    except Exception:
        return True


def internal_login_id(name: str) -> str:
    digest=hashlib.sha256(name.encode("utf-8")).hexdigest()[:32]
    return f"pin-{digest}@jj.invalid"


def _scrub_legacy_emails(con) -> None:
    rows=con.execute("SELECT id,email FROM users").fetchall()
    for row in rows:
        rd=dict(row); email=str(rd.get("email") or "")
        if email.endswith("@jj.invalid"):
            continue
        con.execute("UPDATE users SET email=? WHERE id=?",(f"legacy-{int(rd['id'])}@jj.invalid",rd["id"]))


def _ensure_pin_admin(con) -> None:
    name=os.getenv("JJ_ADMIN_NAME","ケンイチロウ").strip() or "ケンイチロウ"
    pin=(os.getenv("JJ_ADMIN_PIN") or "").strip()
    if not (len(pin)==6 and pin.isdigit()):
        return
    login_id=internal_login_id(name)
    row=con.execute("SELECT id FROM users WHERE email=?",(login_id,)).fetchone()
    if not row:
        uid=insert_returning_id(con,"INSERT INTO users(name,email,password_hash,role,arena_chips,xp,approved,disabled,ranking_name,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",(name,login_id,hash_password(pin),"admin",0,0,1,0,name,utcnow()))
    else:
        uid=int(row["id"])
        # v1.19.0 deterministic administrator recovery
        con.execute(
            "UPDATE users SET role='admin',approved=1,disabled=0,name=?,password_hash=? WHERE id=?",
            (name,hash_password(pin),uid),
        )
        # A recovery PIN invalidates previously issued sessions for this account.
        con.execute("DELETE FROM sessions WHERE user_id=?",(uid,))
    old=con.execute("SELECT id FROM users WHERE role='admin' AND id<>?",(uid,)).fetchall()
    for other in old:
        con.execute("UPDATE users SET role='member' WHERE id=?",(other["id"],))
        con.execute("DELETE FROM sessions WHERE user_id=?",(other["id"],))


def _pg_columns(con, table: str) -> set[str]:
    if not IS_POSTGRES: return set()
    rows = con.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=?", (table,)).fetchall()
    return {r["column_name"] for r in rows}


def _columns(con, table: str) -> set[str]:
    if IS_POSTGRES:
        return _pg_columns(con, table)
    try:
        return {r["name"] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()


def _ensure_access_columns(con):
    cols = _columns(con, "users")
    if not cols:
        return
    if "approved" not in cols:
        con.execute("ALTER TABLE users ADD COLUMN approved INTEGER NOT NULL DEFAULT 1")
    if "disabled" not in cols:
        con.execute("ALTER TABLE users ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0")
    if "ranking_name" not in cols:
        con.execute("ALTER TABLE users ADD COLUMN ranking_name TEXT")
    # Every account that existed before approval was introduced is trusted as an existing member.
    con.execute("UPDATE users SET approved=1 WHERE approved IS NULL")
    con.execute("UPDATE users SET disabled=0 WHERE disabled IS NULL")
    con.execute("UPDATE users SET ranking_name=name WHERE ranking_name IS NULL OR ranking_name=''")


def _migrate_legacy_beta(con):
    if not IS_POSTGRES: return
    cols = _pg_columns(con, "users")
    if cols:
        for col, typ in (("password_hash","TEXT"),("arena_chips","INTEGER NOT NULL DEFAULT 0"),("created_at","TEXT"),("ranking_name","TEXT")):
            con.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {typ}")
        cols = _pg_columns(con, "users")
        if "ph" in cols: con.execute("UPDATE users SET password_hash=ph WHERE password_hash IS NULL")
        if "chips" in cols:
            con.execute("UPDATE users SET arena_chips=COALESCE(NULLIF(arena_chips,0),chips,0) WHERE arena_chips IS NULL OR arena_chips=0")
        else:
            con.execute("UPDATE users SET arena_chips=0 WHERE arena_chips IS NULL")
        if "xp" in cols:
            con.execute("UPDATE users SET xp=0 WHERE xp IS NULL")
        if "role" in cols:
            con.execute("UPDATE users SET role='member' WHERE role IS NULL OR role='' ")
        con.execute("ALTER TABLE users ALTER COLUMN arena_chips SET DEFAULT 0")
        con.execute("ALTER TABLE users ALTER COLUMN arena_chips SET NOT NULL")
        if "xp" in cols:
            con.execute("ALTER TABLE users ALTER COLUMN xp SET DEFAULT 0")
            con.execute("ALTER TABLE users ALTER COLUMN xp SET NOT NULL")
        con.execute("UPDATE users SET created_at=? WHERE created_at IS NULL", (utcnow(),))
        con.execute("UPDATE users SET ranking_name=name WHERE ranking_name IS NULL OR ranking_name='' ")
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



def _ensure_online_hand_columns(con):
    cols=_columns(con,"online_hands")
    if not cols:
        return
    if "voided" not in cols:
        con.execute("ALTER TABLE online_hands ADD COLUMN voided INTEGER NOT NULL DEFAULT 0")
    if "void_reason" not in cols:
        con.execute("ALTER TABLE online_hands ADD COLUMN void_reason TEXT")
    if "voided_at" not in cols:
        con.execute("ALTER TABLE online_hands ADD COLUMN voided_at TEXT")
    if "voided_by" not in cols:
        con.execute("ALTER TABLE online_hands ADD COLUMN voided_by INTEGER")


def _ensure_entry_chip_columns(con):
    cols = _columns(con, "entries")
    if not cols:
        return
    for name in ("chip_1", "chip_5", "chip_10", "chip_25", "chip_100", "chip_500"):
        if name not in cols:
            con.execute(f"ALTER TABLE entries ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0")


def cleanup_duplicate_kenichiro_users() -> int:
    """Keep the admin ケンイチロウ account and remove older duplicate member accounts.

    Foreign-key ownership is reassigned to the retained admin account before deletion.
    Sessions belonging to duplicates are deleted rather than transferred.
    The operation is idempotent and returns the number of removed users.
    """
    target = "ケンイチロウ"
    with connect() as con:
        admin = con.execute(
            "SELECT id FROM users WHERE name=? AND role='admin' ORDER BY id LIMIT 1",
            (target,),
        ).fetchone()
        if not admin:
            return 0
        keep_id = int(admin["id"])
        dup_rows = con.execute(
            "SELECT id FROM users WHERE name=? AND id<>? ORDER BY id",
            (target, keep_id),
        ).fetchall()
        dup_ids = [int(r["id"]) for r in dup_rows]
        if not dup_ids:
            return 0

        refs: list[tuple[str, str]] = []
        if IS_POSTGRES:
            rows = con.execute("""
                SELECT DISTINCT tc.table_name, kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name=kcu.constraint_name AND tc.table_schema=kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                  ON tc.constraint_name=ccu.constraint_name AND tc.table_schema=ccu.table_schema
                WHERE tc.constraint_type='FOREIGN KEY'
                  AND ccu.table_schema='public' AND ccu.table_name='users' AND ccu.column_name='id'
            """).fetchall()
            refs = [(str(r["table_name"]), str(r["column_name"])) for r in rows]
        else:
            tables = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            for row in tables:
                table = str(row["name"])
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
                    continue
                for fk in con.execute(f'PRAGMA foreign_key_list("{table}")').fetchall():
                    fd = dict(fk)
                    if str(fd.get("table")) == "users" and str(fd.get("to")) == "id":
                        refs.append((table, str(fd.get("from"))))

        refs = [
            (table, col) for table, col in refs
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table)
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", col)
        ]
        for dup_id in dup_ids:
            for table, col in refs:
                if table == "sessions":
                    con.execute(f'DELETE FROM "{table}" WHERE "{col}"=?', (dup_id,))
                else:
                    con.execute(f'UPDATE "{table}" SET "{col}"=? WHERE "{col}"=?', (keep_id, dup_id))
            con.execute("DELETE FROM users WHERE id=?", (dup_id,))
        return len(dup_ids)


PROFILE_COLUMNS = (
    ("profile_grade", "TEXT"),
    ("profile_faculty", "TEXT"),
    ("profile_department", "TEXT"),
    ("profile_hometown", "TEXT"),
    ("profile_hobbies", "TEXT"),
    ("profile_bio", "TEXT"),
    ("profile_avatar", "TEXT"),
    ("profile_visible", "INTEGER NOT NULL DEFAULT 1"),
    ("profile_updated_at", "TEXT"),
)


def ensure_profile_columns() -> None:
    """Add optional member-profile fields without changing existing auth semantics."""
    with connect() as con:
        if IS_POSTGRES:
            for col, typ in PROFILE_COLUMNS:
                con.execute(f'ALTER TABLE users ADD COLUMN IF NOT EXISTS "{col}" {typ}')
            con.execute("UPDATE users SET profile_visible=1 WHERE profile_visible IS NULL")
        else:
            cols = {str(r["name"]) for r in con.execute("PRAGMA table_info(users)").fetchall()}
            for col, typ in PROFILE_COLUMNS:
                if col not in cols:
                    con.execute(f'ALTER TABLE users ADD COLUMN "{col}" {typ}')
            con.execute("UPDATE users SET profile_visible=1 WHERE profile_visible IS NULL")


def init_db():
    idcol = "BIGSERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    schema = f"""
    CREATE TABLE IF NOT EXISTS users (id {idcol}, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, password_hash TEXT, role TEXT NOT NULL DEFAULT 'member', arena_chips INTEGER NOT NULL DEFAULT 0, xp INTEGER NOT NULL DEFAULT 0, approved INTEGER NOT NULL DEFAULT 1, disabled INTEGER NOT NULL DEFAULT 0, ranking_name TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires_at TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS entries (id TEXT PRIMARY KEY, date TEXT NOT NULL, name TEXT NOT NULL, remaining INTEGER NOT NULL, reentries INTEGER NOT NULL, initial INTEGER NOT NULL, points INTEGER NOT NULL, game TEXT, game_type TEXT, source TEXT, created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL, chip_1 INTEGER NOT NULL DEFAULT 0, chip_5 INTEGER NOT NULL DEFAULT 0, chip_10 INTEGER NOT NULL DEFAULT 0, chip_25 INTEGER NOT NULL DEFAULT 0, chip_100 INTEGER NOT NULL DEFAULT 0, chip_500 INTEGER NOT NULL DEFAULT 0);
    CREATE INDEX IF NOT EXISTS idx_entries_name_date ON entries(name,date);
    CREATE TABLE IF NOT EXISTS schedules (id {idcol}, date TEXT NOT NULL, time TEXT NOT NULL, room TEXT NOT NULL, title TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', created_by INTEGER REFERENCES users(id), created_at TEXT);
    CREATE TABLE IF NOT EXISTS announcements (id {idcol}, kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, url TEXT NOT NULL DEFAULT '', date TEXT NOT NULL, created_by INTEGER REFERENCES users(id), created_at TEXT);
    CREATE TABLE IF NOT EXISTS threads (id {idcol}, title TEXT NOT NULL, body TEXT NOT NULL, author_id INTEGER REFERENCES users(id), author_name TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS replies (id {idcol}, thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE, body TEXT NOT NULL, author_id INTEGER REFERENCES users(id), author_name TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS tables (id TEXT PRIMARY KEY, name TEXT NOT NULL, owner_id INTEGER REFERENCES users(id), state_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS table_messages (id {idcol}, table_id TEXT NOT NULL REFERENCES tables(id) ON DELETE CASCADE, user_id INTEGER REFERENCES users(id), author_name TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS online_hands (hand_id TEXT PRIMARY KEY, table_id TEXT NOT NULL, hand_no INTEGER NOT NULL, gross_pot_bb NUMERIC NOT NULL, rake_bb NUMERIC NOT NULL, played_at TEXT NOT NULL, month TEXT NOT NULL, voided INTEGER NOT NULL DEFAULT 0, void_reason TEXT, voided_at TEXT, voided_by INTEGER REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS online_hand_results (id TEXT PRIMARY KEY, hand_id TEXT NOT NULL REFERENCES online_hands(hand_id) ON DELETE CASCADE, table_id TEXT NOT NULL, user_id INTEGER REFERENCES users(id), ranking_name TEXT NOT NULL, result_bb NUMERIC NOT NULL, points NUMERIC NOT NULL, month TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_online_results_rank_month ON online_hand_results(ranking_name,month);
    CREATE INDEX IF NOT EXISTS idx_online_results_user_created ON online_hand_results(user_id,created_at);
    """
    with connect() as con:
        _migrate_legacy_beta(con); con.executescript(schema); _ensure_access_columns(con); _ensure_online_hand_columns(con); _ensure_entry_chip_columns(con)
        _scrub_legacy_emails(con)
        _ensure_pin_admin(con)
        # Online ranking points are a derived value. Keep all historical rows aligned
        # with the current 1bb -> point conversion rule after upgrades.
        con.execute("UPDATE online_hand_results SET points=result_bb * ?", (ONLINE_POINTS_PER_BB,))
        # Import the original beta's aggregate table once if present.
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
            state.update({"name":name,"max_seats":TABLE_MAX_SEATS,"small_blind":TABLE_SB,"big_blind":TABLE_BB,"min_buyin":TABLE_STARTING_STACK,"max_buyin":TABLE_STARTING_STACK,"rake_percent":RAKE_PERCENT,"rake_cap":TABLE_BB*RAKE_CAP_BB})
            # A legacy in-progress hand cannot be settled safely because it has no starting-stack snapshot.
            if state.get("status") == "playing" and not (state.get("hand") or {}).get("starting_stacks"):
                state["status"] = "waiting"; state["hand"] = None
                for player in state.get("seats", []):
                    player.update({"in_hand":False,"folded":False,"all_in":False,"round_bet":0,"contributed":0,"cards":[]})
        else:
            state = blank_table_state(table_id=tid,name=name,max_seats=TABLE_MAX_SEATS,small_blind=TABLE_SB,big_blind=TABLE_BB,min_buyin=TABLE_STARTING_STACK,max_buyin=TABLE_STARTING_STACK)
            state.update({"rake_percent":RAKE_PERCENT,"rake_cap":TABLE_BB*RAKE_CAP_BB})
            con.execute("INSERT INTO tables(id,name,owner_id,state_json,created_at,updated_at) VALUES (?,?,?,?,?,?)",(tid,name,None,json.dumps(state,ensure_ascii=False),utcnow(),utcnow()))
            continue
        con.execute("UPDATE tables SET name=?,state_json=?,updated_at=? WHERE id=?",(name,json.dumps(state,ensure_ascii=False),utcnow(),tid))


def seed_if_needed():
    with connect() as con:
        _ensure_pin_admin(con)
        if con.execute("SELECT COUNT(*) c FROM entries").fetchone()["c"] == 0:
            for name, months in SUMMER.items():
                for month, points in months.items():
                    con.execute("INSERT OR IGNORE INTO entries(id,date,name,remaining,reentries,initial,points,game,game_type,source,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",(f"summer-{name}-{month}",month+"-01",name,0,0,1,points,"Summer aggregate","ring","JJ 2026 Summer Season",utcnow()))
        if con.execute("SELECT COUNT(*) c FROM announcements").fetchone()["c"] == 0:
            con.execute("INSERT INTO announcements(kind,title,body,url,date,created_at) VALUES (?,?,?,?,?,?)",("club","JJ Arena v1","共有運用に向けた公開版です。ランキング・予定・戦略議論・固定2卓の6-max NLHを利用できます。","","2026-09-06",utcnow()))
        if con.execute("SELECT COUNT(*) c FROM threads").fetchone()["c"] == 0:
            con.execute("INSERT INTO threads(title,body,author_name,created_at) VALUES (?,?,?,?)",("ハンドレビュー / 戦略議論","気になったハンド、ベットサイズ、ICM、エクスプロイトなどを投稿できます。","JJ Arena",utcnow()))
        _ensure_fixed_tables(con)


def japan_month(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    return dt.astimezone(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m")


def _record_online_hand(con, state: dict[str, Any]) -> dict[str, Any] | None:
    hand = state.get("hand") or {}
    result = state.get("last_result") or {}
    if hand.get("phase") != "complete" or not hand.get("id"):
        return None
    hand_id = str(hand["id"]); bb = max(1, int(state.get("big_blind", TABLE_BB)))
    played_at = utcnow(); month = japan_month()
    gross_bb = round(float(result.get("gross_pot", 0)) / bb, 2)
    rake_bb = round(float(result.get("rake", 0)) / bb, 2)
    con.execute("INSERT OR IGNORE INTO online_hands(hand_id,table_id,hand_no,gross_pot_bb,rake_bb,played_at,month) VALUES (?,?,?,?,?,?,?)",
                (hand_id,state["id"],int(state.get("hand_no",0)),gross_bb,rake_bb,played_at,month))
    rows = []
    for net in result.get("net_results", []):
        uid = int(net["user_id"]); amount = int(net.get("amount",0))
        user = con.execute("SELECT name,ranking_name FROM users WHERE id=?", (uid,)).fetchone()
        ud = dict(user) if user else {}
        ranking_name = ud.get("ranking_name") or ud.get("name") or net.get("name")
        result_bb = round(amount / bb, 2)
        points = round(result_bb * ONLINE_POINTS_PER_BB, 2)
        rid = f"{hand_id}:{uid}"
        con.execute("INSERT OR IGNORE INTO online_hand_results(id,hand_id,table_id,user_id,ranking_name,result_bb,points,month,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (rid,hand_id,state["id"],uid,ranking_name,result_bb,points,month,played_at))
        rows.append({"user_id":uid,"ranking_name":ranking_name,"result_bb":result_bb,"points":points})
    return {"hand_id":hand_id,"rake_bb":rake_bb,"results":rows}


def record_online_hand(state: dict[str, Any]) -> dict[str, Any] | None:
    with connect() as con:
        return _record_online_hand(con, state)


def save_table_state(state: dict[str, Any]) -> None:
    """Atomically settle a completed hand and persist the table state."""
    hand = state.get("hand") or {}
    with connect() as con:
        if hand.get("phase") == "complete" and not hand.get("result_persisted"):
            _record_online_hand(con, state)
            hand["result_persisted"] = True
        con.execute("UPDATE tables SET state_json=?,name=?,updated_at=? WHERE id=?",
                    (json.dumps(state, ensure_ascii=False), state["name"], utcnow(), state["id"]))


def _session_key(token: str) -> str:
    # Store only a one-way digest for newly issued sessions. Legacy plaintext rows are
    # still accepted until they naturally expire so existing beta users are not
    # forcibly signed out by this migration.
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id:int)->str:
    token=secrets.token_urlsafe(32); expires=datetime.now(timezone.utc)+timedelta(days=14)
    with connect() as con:
        con.execute("DELETE FROM sessions WHERE expires_at < ?",(utcnow(),))
        con.execute("INSERT INTO sessions(token,user_id,expires_at,created_at) VALUES (?,?,?,?)",(_session_key(token),user_id,expires.isoformat(),utcnow()))
    return token


def delete_session(token:str|None)->None:
    if token:
        with connect() as con:
            con.execute("DELETE FROM sessions WHERE token=? OR token=?",(_session_key(token),token))


def delete_user_sessions(user_id:int, keep_token:str|None=None)->None:
    with connect() as con:
        if keep_token:
            key=_session_key(keep_token)
            con.execute("DELETE FROM sessions WHERE user_id=? AND token<>? AND token<>?",(user_id,key,keep_token))
        else:
            con.execute("DELETE FROM sessions WHERE user_id=?",(user_id,))


def get_user_by_token(token:str|None)->dict[str,Any]|None:
    if not token: return None
    key=_session_key(token)
    with connect() as con:
        row=con.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE (s.token=? OR s.token=?) AND s.expires_at > ?",(key,token,utcnow())).fetchone()
    return dict(row) if row else None
