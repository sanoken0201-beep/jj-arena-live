"""Allow kana and Latin account names without rewriting the frozen v1.24.4 core.

The PIN endpoint is also the registration endpoint.  The old core normalized
hiragana to katakana unconditionally; this policy preserves new spellings while
allowing existing users to keep logging in with their former input spelling.
Canonical-equivalent names remain reserved by account_name_safety and bans.
"""
from __future__ import annotations

import re
import unicodedata

from fastapi import HTTPException

import account_name_safety

# Keep the existing 2-20 character policy.  NFKC accepts half-width kana.
_NAME = re.compile(r"[A-Za-zぁ-ゖァ-ヺー・]{2,20}\Z")


def validate_name(value: str) -> str:
    name = unicodedata.normalize("NFKC", str(value or "")).strip()
    name = name.replace(" ", "").replace("\u3000", "")
    if not _NAME.fullmatch(name):
        raise HTTPException(
            400,
            "名前はひらがな・カタカナ・英字の2〜20文字で入力してください",
        )
    return name


def _legacy_katakana(name: str) -> str:
    return "".join(
        chr(ord(char) + 0x60) if 0x3041 <= ord(char) <= 0x3096 else char
        for char in name
    )


def install(server, db) -> None:
    """Patch only the runtime name normalizer used by the canonical PIN route.

    The safety and permanent-ban wrappers call server.normalize_login_name at
    request time, so every layer agrees on which account a spelling denotes.
    """
    if getattr(server, "_jj_multi_script_names_installed", False):
        return

    def normalize_login_name(value: str) -> str:
        name = validate_name(value)
        legacy = _legacy_katakana(name)
        # Prefer an exact live account to preserve its stored display spelling.
        # The indexed email lookup avoids a user-list scan for normal logins.
        with db.connect() as con:
            row = con.execute(
                "SELECT name FROM users WHERE email=? AND deleted_at IS NULL",
                (server.internal_login_id(name),),
            ).fetchone()
            if row:
                return str(row["name"])

            # Before this feature, entering たろう meant logging in as タロウ.
            # Honor that existing behavior only when such an account exists.
            if legacy != name:
                row = con.execute(
                    "SELECT name FROM users WHERE email=? AND deleted_at IS NULL",
                    (server.internal_login_id(legacy),),
                ).fetchone()
                if row:
                    return str(row["name"])

            # A newly registered hiragana name should likewise be reachable
            # using katakana, and Latin names should be case-insensitive.
            # Scan only on a miss: normal logins use the indexed lookup above.
            aliases = [
                str(row["name"])
                for row in con.execute(
                    "SELECT name FROM users WHERE deleted_at IS NULL"
                ).fetchall()
                if account_name_safety.confusable(name, row["name"])
            ]
            if len(aliases) == 1:
                return aliases[0]

        # A new hiragana name is stored as hiragana, not converted to katakana.
        # Registration still checks confusable active names and permanent bans.
        return name

    server.normalize_login_name = normalize_login_name
    server._jj_multi_script_names_installed = True


__all__ = ["validate_name", "install"]
