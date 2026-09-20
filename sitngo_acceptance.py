"""Machine-readable Sit&Go acceptance coverage.

Each adopted production contract maps to at least one active Sit&Go regression.
This is traceability metadata, not a substitute for the regressions themselves.
"""
from __future__ import annotations

SITNGO_ACCEPTANCE: dict[str, dict[str, object]] = {
    "lifecycle_and_registration": {
        "description": "Scheduled 2-6 player freezeout lifecycle, registration, cancellation, one-running guard, and queued-event handoff.",
        "tests": (
            "smoke_test_sitngo_phase1.py",
            "smoke_test_sitngo_freezeout_contract.py",
        ),
    },
    "isolated_tournament_engine": {
        "description": "Tournament state and rules remain isolated from Ring settlement and cash-only controls.",
        "tests": (
            "smoke_test_sitngo_gameplay.py",
            "smoke_test_sitngo_api.py",
        ),
    },
    "official_point_accounting": {
        "description": "Entry debit, negative balances, exact refunds, locked terms, escrow integrity, payouts, ties, and idempotent settlement.",
        "tests": ("smoke_test_sitngo_points.py",),
    },
    "chip_and_bba_accounting": {
        "description": "Permanent 100-point unit, BBA dead money, exact-once POT display, raise increments, split pots, and conservation.",
        "tests": ("smoke_test_sitngo_chip_rules.py",),
    },
    "button_blinds_and_reopen_rules": {
        "description": "Dead-button movement, heads-up button/SB behavior, deal order, and cumulative short-all-in reopening.",
        "tests": ("smoke_test_sitngo_tournament_rules.py",),
    },
    "simultaneous_elimination_ranking": {
        "description": "TDA post-ante comparison stacks, equal-stack ties, and finishing-place assignment.",
        "tests": ("smoke_test_sitngo_elimination_ranking.py",),
    },
    "twelve_hand_blind_levels": {
        "description": "New tournaments advance blinds only after each 12 completed hands and never from elapsed time.",
        "tests": ("smoke_test_sitngo_hand_levels.py",),
    },
    "action_identity_and_timeout_safety": {
        "description": "Action/hand/turn identity, duplicate rejection, stale-action rejection, timeout boundary protection, and automatic timeout action.",
        "tests": ("smoke_test_sitngo_action_safety.py",),
    },
    "authenticated_table_api_and_privacy": {
        "description": "Authenticated HTTP/WebSocket table access, participant chat, history privacy, and cash-only endpoint rejection.",
        "tests": ("smoke_test_sitngo_api.py",),
    },
    "multi_session_convergence": {
        "description": "Independent member sessions converge on one authoritative revision, hand, turn, and stack state.",
        "tests": ("smoke_test_sitngo_multi_session.py",),
    },
    "single_process_runtime_model": {
        "description": "Production process model remains compatible with in-process table locks and single scheduler ownership.",
        "tests": ("smoke_test_sitngo_process_model.py",),
    },
    "state_backup_and_restart_recovery": {
        "description": "Bounded meaningful state generations, restart continuation, corruption validation, and same-event automatic restore.",
        "tests": ("smoke_test_sitngo_resilience.py",),
    },
    "compatibility_and_browser_build_ownership": {
        "description": "Legacy timing metadata remains compatibility-only and Sit&Go browser transforms have one deterministic build owner.",
        "tests": ("smoke_test_sitngo_contract_consolidation.py",),
    },
    "growing_history_and_chat_reads": {
        "description": "Event-scoped reverse-chronological history and chat reads retain their composite index contract.",
        "tests": ("smoke_test_sitngo_storage_indexes.py",),
    },
    "player_and_admin_browser_contract": {
        "description": "Phone/desktop tournament controls, finished point statement, admin settings, telemetry, and alert presentation.",
        "tests": ("smoke_test_sitngo_browser.py",),
    },
}

__all__ = ["SITNGO_ACCEPTANCE"]
