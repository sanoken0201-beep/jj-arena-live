from __future__ import annotations

"""Machine-readable lifecycle inventory for JJ Arena product surfaces.

The purpose is operational: compatibility code must not be mistaken for an
active feature and retired surfaces must not silently reappear in navigation or
write paths. Data-retention compatibility is intentionally separate from UI
exposure.
"""

ACTIVE = frozenset(
    {
        "auth.name_pin",
        "auth.self_pin_change",
        "admin.console",
        "admin.console_api",
        "points.official_ledger",
        "ring.public_table_a",
        "ring.websocket_actions",
        "poker_lab",
        "hand_analysis",
        "announcements",
        "rankings",
        "home",
        "sitngo.root_integration",
    }
)

COMPATIBILITY_ONLY = frozenset(
    {
        "ring.internal_table_b",
        "schedule.backend_data",
        "discussion.backend_data",
        "app_legacy.rollback_oracle",
        "browser.historical_transform_units",
    }
)

RETIRED = frozenset(
    {
        "admin.legacy_member_list",
        "admin.legacy_member_patch",
        "admin.legacy_member_pin_reset",
        "auth.email_signup",
        "auth.email_login",
        "ring.public_table_selection",
        "nav.schedule",
        "nav.discussion",
        "live_table.primary_chat_log",
    }
)


def assert_disjoint() -> None:
    groups = (ACTIVE, COMPATIBILITY_ONLY, RETIRED)
    for index, left in enumerate(groups):
        for right in groups[index + 1 :]:
            overlap = left & right
            if overlap:
                raise RuntimeError(f"feature lifecycle overlap: {sorted(overlap)}")


assert_disjoint()

__all__ = ["ACTIVE", "COMPATIBILITY_ONLY", "RETIRED", "assert_disjoint"]
