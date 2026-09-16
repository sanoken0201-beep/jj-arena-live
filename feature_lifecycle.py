from __future__ import annotations

"""Machine-readable lifecycle map for JJ Arena product surfaces.

This prevents hidden/legacy features from drifting back into the primary UI or
being reused accidentally by new work.  Compatibility-retained features may
keep their data/backend for history or rollback, but are not primary product
surfaces.
"""

ACTIVE = {
    "auth.pin_login",
    "home",
    "ranking",
    "ring.single_public_table",
    "poker_lab",
    "announcements",
    "official_points",
    "admin.console",
    "hand_analysis",
    "sitngo",
}

COMPATIBILITY_RETAINED = {
    "schedule.backend": "Historical activity dates remain readable and are surfaced in Announcements.",
    "discussion.backend": "Historical strategy-discussion data/routes are retained for rollback/history only.",
    "ring.second_internal_table": "Internal rollback/data compatibility only; never public table selection.",
    "frontend.historical_transforms": "Frozen compatibility compiler input; production entrypoint is frontend_build_pipeline.py.",
}

RETIRED = {
    "admin.legacy_members_api": "410 tombstone; use /api/admin/console/users*.",
    "schedule.primary_navigation": "Merged into Announcements.",
    "discussion.primary_navigation": "Removed from primary navigation.",
    "ring.public_multi_table_selection": "Public contract is one ring table.",
    "poker.in_hand_chat_surface": "Persisted history/review remains; live chat surface removed.",
    "poker.live_action_log_surface": "Post-hand review is the supported history surface.",
    "poker.bet_size_presets": "Manual numeric sizing is the supported input.",
    "auth.email_signup_login": "410 compatibility endpoints; PIN login is canonical.",
}


__all__ = ["ACTIVE", "COMPATIBILITY_RETAINED", "RETIRED"]
