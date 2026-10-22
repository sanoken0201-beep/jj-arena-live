"""Block canonical-equivalent account names and ranking aliases.

The canonical PIN endpoint doubles as registration.  Install an explicit
transactional registration guard instead of modifying the immutable core.
Existing users keep the core's original login, rate-limiting and PIN behavior.
"""
from __future__ import annotations

import threading
import unicodedata

from fastapi import HTTPException

_LOCK_KEY = 2026101901
_NAME_LOCK = threading.RLock()  # Single-worker app: coordinates all application name writers.


def identity_key(value: str) -> str:
    """NFKC/casefold, hiragana -> katakana, remove visual separators."""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    chars = []
    for ch in text:
        code = ord(ch)
        if 0x3041 <= code <= 0x3096:
            ch = chr(code + 0x60)
        if ch.isspace() or ch in ("・", "･", "-", "_", "\u200b", "\u200c", "\u200d"):
            continue
        chars.append(ch)
    return "".join(chars)


def confusable(left: str, right: str) -> bool:
    """Reject only canonical-equivalent names, never edit-distance neighbors.

    A one-character difference may denote a distinct person (e.g. ケンジ and
    ケンタ). Similarity alone is not proof of impersonation.
    """
    a, b = identity_key(left), identity_key(right)
    return bool(a and b and a == b)


def conflict(con, candidate: str, *, exclude_user_id: int | None = None) -> bool:
    # Disabled users retain ownership of their names; deleted generations do not.
    query = "SELECT id,name,ranking_name FROM users WHERE deleted_at IS NULL"
    args = []
    if exclude_user_id is not None:
        query += " AND id<>?"
        args.append(exclude_user_id)
    for row in con.execute(query, args).fetchall():
        if confusable(candidate, row["name"]) or confusable(candidate, row["ranking_name"]):
            return True
    return False


def _serialize(con, db) -> None:
    # Registration and admin name edits must acquire this same lock BEFORE
    # reading possible competitors. SQLite CI and production PostgreSQL agree.
    if getattr(db, "IS_POSTGRES", False):
        con.execute("SELECT pg_advisory_xact_lock(?)", (_LOCK_KEY,))
    else:
        con.execute("BEGIN IMMEDIATE")


def _route(app, path: str, method: str):
    return next((
        r for r in app.router.routes
        if getattr(r, "path", None) == path
        and method in (getattr(r, "methods", None) or set())
    ), None)


def install(app, server, db) -> None:
    if getattr(app.state, "jj_account_name_safety_installed", False):
        return
    pin = _route(app, "/api/auth/pin", "POST")
    admin = _route(app, "/api/admin/console/users/{uid}", "PATCH")
    if not pin or not admin or not getattr(pin, "dependant", None) or not getattr(admin, "dependant", None):
        raise RuntimeError("account name safety requires active PIN and canonical admin routes")

    original_pin = pin.dependant.call
    original_admin = admin.dependant.call

    def safe_pin(payload, response, request):
        name = server.normalize_login_name(payload.name)
        secret = server.validate_pin(payload.pin)
        login_id = server.internal_login_id(name)
        created = False

        # No new-account policy is applied to existing logins: they must still
        # be able to sign in or receive the normal incorrect-PIN response.
        with db.connect() as con:
            present = con.execute("SELECT id FROM users WHERE email=?", (login_id,)).fetchone()
        if not present:
            # Rate-limit validation BEFORE creating an account. The original
            # endpoint continues to account for incorrect PIN attempts.
            server._check_login_rate(request, login_id)
            with _NAME_LOCK:
                with db.connect() as con:
                    _serialize(con, db)
                    present = con.execute("SELECT id FROM users WHERE email=?", (login_id,)).fetchone()
                    if not present:
                        if conflict(con, name):
                            raise HTTPException(
                                409,
                                "表記を正規化すると同一になるアカウント名が既に存在します。別の名前を使用するか運営に確認してください",
                            )
                        db.insert_returning_id(
                            con,
                            "INSERT INTO users(name,email,password_hash,role,arena_chips,xp,approved,disabled,ranking_name,created_at) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (name, login_id, db.hash_password(secret), "member", 0, 0, 1, 0, name, db.utcnow()),
                        )
                        created = True
        result = original_pin(payload=payload, response=response, request=request)
        if created:
            result = {**result, "created": True}
        return result

    def safe_admin_update(uid, p, user):
        # Preserve harmless repairs for historical duplicate mappings. Enforce
        # the rule only when changing an active alias or re-enabling a member.
        with db.connect() as con:
            row = con.execute(
                "SELECT ranking_name,name,disabled,deleted_at FROM users WHERE id=?",
                (uid,),
            ).fetchone()
        if not row or row["deleted_at"]:
            return original_admin(uid=uid, p=p, user=user)
        old = str(row["ranking_name"] or row["name"])
        proposed = getattr(p, "ranking_name", None)
        candidate = str(proposed).strip() if proposed is not None else old
        current_disabled = bool(row["disabled"])
        new_disabled = current_disabled if getattr(p, "disabled", None) is None else bool(p.disabled)
        if (not new_disabled and (candidate != old or (current_disabled and p.disabled is False))):
            # Lock across the original write: the wrapper and PIN registrations
            # serialize their name checks even when the endpoint opens a second
            # DB transaction for its canonical history migration.
            with _NAME_LOCK:
                if getattr(db, "IS_POSTGRES", False):
                    # Hold a PostgreSQL advisory lock while the existing
                    # canonical endpoint completes its separate transaction.
                    with db.connect() as con:
                        _serialize(con, db)
                        if conflict(con, candidate, exclude_user_id=uid):
                            raise HTTPException(409, f"ランキング名「{candidate}」は他のアカウント名と正規化後に一致するため使用できません")
                        return original_admin(uid=uid, p=p, user=user)
                # The canonical endpoint opens a new SQLite write connection:
                # holding BEGIN IMMEDIATE here would deadlock that write.
                with db.connect() as con:
                    if conflict(con, candidate, exclude_user_id=uid):
                        raise HTTPException(409, f"ランキング名「{candidate}」は他のアカウント名と正規化後に一致するため使用できません")
                return original_admin(uid=uid, p=p, user=user)
        return original_admin(uid=uid, p=p, user=user)

    pin.dependant.call = safe_pin
    pin.endpoint = safe_pin
    admin.dependant.call = safe_admin_update
    admin.endpoint = safe_admin_update
    app.state.jj_account_name_safety_installed = True


__all__ = ["confusable", "identity_key", "install"]
