from __future__ import annotations

"""Machine-readable lifecycle inventory for JJ Arena product surfaces.

Stage 4 does not delete historical data or rollback code. It makes the product
boundary explicit so compatibility paths cannot accidentally be treated as
active features and retired surfaces cannot silently return through later UI or
API work.
"""

ACTIVE = "active"
COMPATIBILITY_ONLY = "compatibility_only"
RETIRED = "retired"

FEATURES: dict[str, dict[str, str]] = {
    # Active player/admin product surfaces.
    "auth.name_pin": {"status": ACTIVE, "owner": "auth", "note": "Canonical sign-in contract."},
    "auth.self_pin_change": {"status": ACTIVE, "owner": "auth", "note": "Current-PIN verified self-service change."},
    "admin.console": {"status": ACTIVE, "owner": "admin", "note": "Canonical administrator UI at /admin."},
    "admin.console_api": {"status": ACTIVE, "owner": "admin", "note": "Canonical account reads and mutations."},
    "points.official_ledger": {"status": ACTIVE, "owner": "points", "note": "Official point ledger and ranking integration."},
    "ring.public_table_a": {"status": ACTIVE, "owner": "ring", "note": "Only public Ring table."},
    "ring.websocket_actions": {"status": ACTIVE, "owner": "ring", "note": "Live Ring state/action transport."},
    "poker_lab": {"status": ACTIVE, "owner": "analysis", "note": "Poker Lab remains a supported product surface."},
    "hand_analysis": {"status": ACTIVE, "owner": "analysis", "note": "Hand history/review and analytics."},
    "announcements": {"status": ACTIVE, "owner": "club", "note": "Canonical club notice destination."},
    "rankings": {"status": ACTIVE, "owner": "points", "note": "Current ranking presentation."},
    "home": {"status": ACTIVE, "owner": "club", "note": "Current home overview."},
    "sitngo.root_integration": {"status": ACTIVE, "owner": "sitngo", "note": "Root-level Sit&Go scheduling/gameplay integration."},

    # Retained implementation/data surfaces. These may preserve stale clients,
    # rollback safety or historical records but are not destinations for new
    # product behavior.
    "ring.internal_table_b": {"status": COMPATIBILITY_ONLY, "owner": "ring", "note": "Hidden from the public table list; retained for rollback/data compatibility."},
    "schedule.backend_data": {"status": COMPATIBILITY_ONLY, "owner": "club", "note": "Historical schedule records retained and surfaced through announcements."},
    "discussion.backend_data": {"status": COMPATIBILITY_ONLY, "owner": "club", "note": "Historical discussion data retained; no top-level destination."},
    "ring.table_messages": {"status": COMPATIBILITY_ONLY, "owner": "ring", "note": "Historical/stale-client message compatibility; not a primary live-table surface."},
    "app_legacy.rollback_oracle": {"status": COMPATIBILITY_ONLY, "owner": "runtime", "note": "Emergency rollback/parity oracle only."},
    "browser.historical_transform_units": {"status": COMPATIBILITY_ONLY, "owner": "browser", "note": "Regression-tested build implementation units, not product surfaces."},

    # Retired product surfaces. Compatibility tombstones/data may still exist,
    # but these items must not be reintroduced without an explicit product
    # decision.
    "admin.legacy_member_list": {"status": RETIRED, "owner": "admin", "note": "Replaced by /api/admin/console/users."},
    "admin.legacy_member_patch": {"status": RETIRED, "owner": "admin", "note": "Replaced by /api/admin/console/users/{uid}."},
    "admin.legacy_member_pin_reset": {"status": RETIRED, "owner": "admin", "note": "Replaced by the canonical admin console PIN reset."},
    "auth.email_signup": {"status": RETIRED, "owner": "auth", "note": "Replaced by name + 6-digit PIN access."},
    "auth.email_login": {"status": RETIRED, "owner": "auth", "note": "Replaced by name + 6-digit PIN access."},
    "ring.public_table_selection": {"status": RETIRED, "owner": "ring", "note": "JJ Arena exposes one public Ring table."},
    "nav.schedule": {"status": RETIRED, "owner": "club", "note": "Schedule is folded into announcements."},
    "nav.discussion": {"status": RETIRED, "owner": "club", "note": "Strategy Discussion is not a top-level destination."},
    "live_table.primary_chat_log": {"status": RETIRED, "owner": "ring", "note": "Live-table primary UI no longer presents chat/live action log."},
}

ACTIVE_FEATURES = frozenset(name for name, meta in FEATURES.items() if meta["status"] == ACTIVE)
COMPATIBILITY_FEATURES = frozenset(
    name for name, meta in FEATURES.items() if meta["status"] == COMPATIBILITY_ONLY
)
RETIRED_FEATURES = frozenset(name for name, meta in FEATURES.items() if meta["status"] == RETIRED)

# Retired API contracts that intentionally remain as explicit tombstones. The
# route name is part of the contract: a later implementation must not silently
# replace a tombstone with a second live code path.
RETIRED_ROUTE_TOMBSTONES: tuple[tuple[str, str, str], ...] = (
    ("GET", "/api/admin/members", "retired_legacy_member_list"),
    ("PATCH", "/api/admin/members/{user_id}", "retired_legacy_member_patch"),
    ("POST", "/api/admin/members/{user_id}/reset-pin", "retired_legacy_member_pin_reset"),
    ("POST", "/api/auth/signup", "legacy_signup_disabled"),
    ("POST", "/api/auth/login", "legacy_login_disabled"),
)

# Compatibility-only backend/data routes are intentionally retained. Their
# presence does not make the corresponding feature an active navigation target.
COMPATIBILITY_ROUTE_CONTRACTS: tuple[tuple[str, str], ...] = (
    ("GET", "/api/schedules"),
    ("POST", "/api/schedules"),
    ("GET", "/api/threads"),
    ("POST", "/api/threads"),
    ("POST", "/api/threads/{thread_id}/replies"),
    ("POST", "/api/tables/{table_id}/chat"),
)


def assert_valid() -> None:
    valid = {ACTIVE, COMPATIBILITY_ONLY, RETIRED}
    unknown = {meta.get("status") for meta in FEATURES.values()} - valid
    if unknown:
        raise RuntimeError(f"unknown feature lifecycle states: {sorted(unknown)}")
    groups = (ACTIVE_FEATURES, COMPATIBILITY_FEATURES, RETIRED_FEATURES)
    for index, left in enumerate(groups):
        for right in groups[index + 1 :]:
            overlap = left & right
            if overlap:
                raise RuntimeError(f"feature lifecycle overlap: {sorted(overlap)}")
    if set().union(*groups) != set(FEATURES):
        raise RuntimeError("feature lifecycle inventory is incomplete")


assert_valid()

__all__ = [
    "ACTIVE",
    "ACTIVE_FEATURES",
    "COMPATIBILITY_ONLY",
    "COMPATIBILITY_FEATURES",
    "COMPATIBILITY_ROUTE_CONTRACTS",
    "FEATURES",
    "RETIRED",
    "RETIRED_FEATURES",
    "RETIRED_ROUTE_TOMBSTONES",
    "assert_valid",
]
