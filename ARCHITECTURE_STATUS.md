# JJ Arena Architecture Status

Updated: 2026-09-17

This document classifies production surfaces so compatibility code is not mistaken for an active product path. `materialized_v1244/` remains the immutable canonical core and is not edited for ordinary product changes. The machine-readable counterpart is `feature_lifecycle.py`.

## Active production surfaces

- Authentication: name + 6-digit PIN via `/api/auth/pin`.
- Self-service PIN change: `/api/auth/change-pin` with current-PIN verification.
- Canonical administration UI: `/admin`.
- Canonical account reads/mutations: `/api/admin/console/...`.
- Official point ledger and ranking integration.
- One public Ring table: `jj-table-a`.
- Ring WebSocket/state/action APIs.
- Poker Lab, hand analysis/review, announcements, rankings and home overview.
- Sit&Go lives in its own root-level integration and data model; it is not changed by this cleanup.

## Compatibility-only surfaces

These remain because historical data, rollback behavior, or tested implementation units may reference them. They must not receive new product behavior.

- Internal historical Ring table B: retained for rollback/data compatibility; not returned by the public table list.
- Schedule backend/data: retained because schedule records are surfaced through announcements, although the dedicated top-level schedule navigation is retired.
- Strategy discussion backend/data: retained for historical data compatibility; not a top-level product destination.
- `app_legacy.py`: emergency rollback/parity oracle only.
- Historical browser transform modules: regression-tested implementation units used by the deterministic build compiler. They are not runtime mutation hooks.

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

The production browser contract is **canonical prebuilt output**:

1. `served_assets.py` compiles the immutable `materialized_v1244/static` input through the historical regression-tested UX stages.
2. `browser_asset_pipeline.py` is the single final orchestration point for safety/consolidation layers.
3. `browser_runtime_consolidation.py` runs last and absorbs the deterministic browser mutations that historically lived in `app.py`.
4. `.jj_build/index.html`, `.jj_build/static/app.js`, `.jj_build/static/styles.css` and `.jj_build/static/sw.js` are therefore the exact canonical browser bytes for a release.
5. `app.py` may perform transport work such as gzip/ETag handling but must not rewrite browser source at request time.

`build_served_assets.py` must not manually call individual final transforms. New browser changes are registered in `browser_asset_pipeline.POST_BUILD_STAGES`, or folded into an existing stage, so ordering remains explicit and testable.

The build manifest records `browser_output_contract=canonical-prebuilt-v1` and the ordered pipeline stages. `smoke_test_structure_consolidation.py` and `smoke_test_feature_lifecycle.py` guard this boundary.

## Test ownership

Tests are grouped by operational concern in `test_suites.py`:

- `auth_security`
- `points_integrity`
- `ring_gameplay`
- `browser_contract`
- `runtime_release`
- `sitngo`

The production release gate selects deterministic production-dependency tests from those groups. Browser/Playwright tests remain in GitHub Actions and are not required inside the Render build image. Lifecycle/structure regressions are part of the browser/security contract so retired surfaces and request-time browser mutations cannot silently return.
