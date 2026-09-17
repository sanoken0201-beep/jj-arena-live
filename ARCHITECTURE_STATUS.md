# JJ Arena Architecture Status

Updated: 2026-09-17

This document classifies production surfaces so compatibility code is not mistaken for an active product path. `materialized_v1244/` remains the immutable canonical core and is not edited for ordinary product changes.

## Active production surfaces

- Authentication: name + 6-digit PIN via `/api/auth/pin`.
- Self-service PIN change: `/api/auth/change-pin` with current-PIN verification.
- Canonical administration UI: `/admin`.
- Canonical account reads/mutations: `/api/admin/console/...`.
- Official point ledger and ranking integration.
- One public Ring table: `jj-table-a`.
- Ring WebSocket/state/action APIs.
- Poker Lab, hand analysis/review, announcements, rankings and home overview.
- Sit&Go lives in its own root-level integration and data model; it is not part of this cleanup.

## Compatibility-only surfaces

These remain because old cached clients or historical data may reference them. They must not receive new product behavior.

- Internal historical Ring table B: retained for rollback/data compatibility; not returned by the public table list.
- Schedule backend/data: retained because schedule records are surfaced through announcements, although the dedicated top-level schedule navigation is hidden.
- Strategy discussion backend/data: retained for historical data compatibility; not a top-level product destination.
- `app_legacy.py`: emergency rollback/parity oracle only.
- Historical browser transform modules: implementation units used by the deterministic build compiler. Production ordering is declared centrally by `browser_asset_pipeline.py`.

## Retired surfaces

These are intentionally unavailable and must not be revived by a later patch without an explicit product decision.

- `GET /api/admin/members` — replaced by `/api/admin/console/users`.
- `PATCH /api/admin/members/{user_id}` — replaced by `/api/admin/console/users/{uid}`.
- `POST /api/admin/members/{user_id}/reset-pin` — replaced by `/api/admin/console/users/{uid}/reset-pin`.
- Legacy email signup/login endpoints.
- Public table selection between A/B.
- Top-level Schedule navigation.
- Top-level Strategy Discussion navigation.
- In-hand chat/live hand-log presentation as a primary live-table surface.

The legacy member-admin URLs remain only as authenticated HTTP 410 tombstones so stale clients fail explicitly instead of falling through to an old implementation.

## Browser build ownership

The browser build is two-tiered:

1. `served_assets.py` compiles the immutable `materialized_v1244/static` input through the historical, regression-tested UX stages.
2. `browser_asset_pipeline.py` is the single production post-build orchestration point for safety/finalization layers.

The final stage, `browser_runtime_consolidation.py`, absorbs the deterministic browser mutations that previously lived in `app.py` at request time. The validated `.jj_build` directory is therefore the canonical browser output. `app.py` may perform transport work such as ETag/gzip handling, but it must not rewrite HTML, JavaScript or CSS source while serving a request.

`build_served_assets.py` must not manually call individual final transforms. New final browser layers are registered in `browser_asset_pipeline.POST_BUILD_STAGES` so ordering is explicit and testable.

## Test ownership

Tests are grouped by operational concern in `test_suites.py`:

- `auth_security`
- `points_integrity`
- `ring_gameplay`
- `browser_contract`
- `runtime_release`
- `sitngo`

The production release gate selects deterministic production-dependency tests from those groups. Browser/Playwright tests remain in GitHub Actions and are not required inside the Render build image.
