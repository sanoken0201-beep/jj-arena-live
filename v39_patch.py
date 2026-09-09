from __future__ import annotations

from pathlib import Path


def apply(root: Path) -> None:
    """Harden the environment-driven administrator recovery path.

    v1.5 introduced ``JJ_ADMIN_PIN`` as an emergency/bootstrap credential, but
    the existing-admin branch only restored role/state and did not replace the
    stored PIN hash. That made a recovery deploy appear successful while PIN
    authentication continued to fail. When a valid six-digit ``JJ_ADMIN_PIN``
    is deliberately present, recovery must be authoritative: update the hash,
    restore the account, and revoke existing sessions.
    """

    db_path = root / "db.py"
    text = db_path.read_text(encoding="utf-8")

    marker = "# v1.19.0 deterministic administrator recovery"
    if marker in text:
        return

    old = '''    else:\n        uid=int(row["id"]); con.execute("UPDATE users SET role='admin',approved=1,disabled=0,name=? WHERE id=?",(name,uid))\n'''
    if old not in text:
        raise RuntimeError("v1.19.0 admin recovery marker missing")

    new = '''    else:\n        uid=int(row["id"])\n        # v1.19.0 deterministic administrator recovery\n        con.execute(\n            "UPDATE users SET role='admin',approved=1,disabled=0,name=?,password_hash=? WHERE id=?",\n            (name,hash_password(pin),uid),\n        )\n        # A recovery PIN invalidates previously issued sessions for this account.\n        con.execute("DELETE FROM sessions WHERE user_id=?",(uid,))\n'''
    text = text.replace(old, new, 1)
    db_path.write_text(text, encoding="utf-8")

    server_path = root / "server.py"
    server = server_path.read_text(encoding="utf-8")
    server = server.replace('version="1.18.6"', 'version="1.19.0"')
    server = server.replace('"version":"1.18.6"', '"version":"1.19.0"')
    server_path.write_text(server, encoding="utf-8")
