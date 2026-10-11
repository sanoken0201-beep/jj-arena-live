"""Preserve delegated administrators when the immutable core initializes.

The canonical 1.24.4 bootstrap rewrites its environment-backed admin and
demotes every other administrator each time init_db()/seed_if_needed() runs.
That behavior predates multi-admin succession and would revoke handover on
Render restarts. Wrap the one bootstrap hook BEFORE importing the core server.
Never edit the golden-master source or mutate permissions on an ordinary boot.
"""
from __future__ import annotations


def install(db) -> None:
    if getattr(db, "_jj_delegated_bootstrap_guard", False):
        return
    legacy_bootstrap = db._ensure_pin_admin

    def preserve_existing_admins(con):
        # If any viable administrator remains, ALL rights/PINs/sessions are
        # authoritative from the audited role-management API. The environment
        # seed is only for first initialization or last-admin disaster recovery.
        columns = db._columns(con, "users")
        extra = " AND deleted_at IS NULL" if "deleted_at" in columns else ""
        viable = con.execute(
            "SELECT id FROM users WHERE role='admin' AND COALESCE(disabled,0)=0"
            + extra + " LIMIT 1"
        ).fetchone()
        if viable:
            return
        legacy_bootstrap(con)

    preserve_existing_admins.__wrapped__ = legacy_bootstrap
    db._ensure_pin_admin = preserve_existing_admins
    db._jj_delegated_bootstrap_guard = True
