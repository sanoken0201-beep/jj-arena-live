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

These remain because old cached clients, historical data, rollback safety or the deterministic browser compiler still depend on them. They are not destinations for new product behavior unless an explicit product decision promotes them back to active status.

- Internal historical Ring table B: retained for rollback/data compatibility; not returned by the public table list.
- Schedule backend/data: retained because historical schedule records are surfaced through announcements, although the dedicated top-level schedule navigation is hidden.
- Strategy discussion backend/data: retained for historical data compatibility; not a top-level product destination.
- Table-message backend/storage: retained for historical/stale-client compatibility; chat is not a primary live-table surface.
- `app_legacy.py`: emergency rollback/parity oracle only and not part of the production import path.
- Historical browser transform modules: implementation units used by the deterministic build compiler. Production ordering is declared centrally by `browser_asset_pipeline.py`.

## Retired surfaces

These are intentionally unavailable as product surfaces and must not be revived by a later patch without an explicit product decision.

- `GET /api/admin/members` — replaced by `/api/admin/console/users`.
- `PATCH /api/admin/members/{user_id}` — replaced by `/api/admin/console/users/{uid}`.
- `POST /api/admin/members/{user_id}/reset-pin` — replaced by `/api/admin/console/users/{uid}/reset-pin`.
- Legacy email signup/login endpoints.
- Public table selection between A/B.
- Top-level Schedule navigation.
- Top-level Strategy Discussion navigation.
- In-hand chat/live hand-log presentation as a primary live-table surface.

The legacy member-admin URLs remain only as authenticated HTTP 410 tombstones so stale clients fail explicitly instead of falling through to an old implementation. Legacy email signup/login likewise remain as explicit HTTP 410 tombstones in the immutable core.

## Feature lifecycle enforcement

`feature_lifecycle.py` is the machine-readable source of truth for Stage 4. Every classified product surface is one of `active`, `compatibility_only`, or `retired`; the three sets are validated as mutually exclusive and complete.

`smoke_test_feature_lifecycle.py` enforces the important product-boundary contracts in an isolated database: retired admin/auth URLs must still resolve only to tombstones, compatibility schedule/discussion data routes must remain available for historical clients, `app_legacy.py` must not enter the production import path, the public Ring table list must expose only `jj-table-a`, and retired Schedule/Discussion navigation must stay absent from the canonical browser build.

Compatibility-only does not mean "safe to build on". New UI, new writes, new API consumers or new business logic must target an active surface unless the lifecycle classification is deliberately changed in the same reviewed release.

## Browser build ownership

The browser build is two-tiered:

1. `served_assets.py` compiles the immutable `materialized_v1244/static` input through the historical, regression-tested UX stages.
2. `browser_asset_pipeline.py` is the single production post-build orchestration point for safety/finalization layers.

The final stage, `browser_runtime_consolidation.py`, absorbs the deterministic browser mutations that previously lived in `app.py` at request time. The validated `.jj_build` directory is therefore the canonical browser output. `app.py` may perform transport work such as ETag/gzip handling, but it must not rewrite HTML, JavaScript or CSS source while serving a request.

`build_served_assets.py` must not manually call individual final transforms. New final browser layers are registered in `browser_asset_pipeline.POST_BUILD_STAGES` so ordering is explicit and testable.

## Repository pruning

Stage 6 removes the obsolete pre-materialization copies of the core from the repository root: `server.py`, `db.py`, `poker_engine.py`, and the old root `static/` tree. These files are not production inputs after the materialized-core cutover and create an import-resolution hazard because ad-hoc bare imports can select an obsolete implementation instead of the canonical core.

The canonical committed core is `materialized_v1244/`; the canonical served browser output remains `.jj_build/`. Production `app.py` imports the runtime through `app_materialized.py`, while `served_assets.py` compiles from `materialized_v1244/static`.

`smoke_test_root_core_pruned.py` is owned by `runtime_release` and selected by the production release gate. It fails if a stale root core/static copy reappears, if the canonical materialized files disappear, or if the production runtime/browser pointers move away from `materialized_v1244` without an explicit architecture change.

Rollback/parity artifacts such as `app_legacy.py`, `runtime_builder.py`, `release_v14/`, `v18_assets/`, and `v54_patch.py` are intentionally outside this Stage 6 guard. Their remaining lifecycle is reviewed separately in Stage 7B.2 rather than being made a permanent dependency of the pruned architecture.

## Test ownership

Stage 5 makes `test_suites.py` the enforceable source of truth for active regression ownership. Tests are grouped by operational concern:

- `auth_security`
- `points_integrity`
- `ring_gameplay`
- `browser_contract`
- `runtime_release`
- `sitngo`

Every test listed in an active suite has exactly one owner. Every test selected by the production release gate must be owned by the same suite that selects it, may appear only once in the release selection, and must be compatible with the Render production dependency set. Browser/Playwright-only tests are explicitly marked and rejected if they are accidentally added to the Render release gate.

`smoke_test_test_ownership.py` validates those contracts and is itself part of `runtime_release`, so ownership drift fails before deployment. `production_release_gate.py` continues to consume `production_release_tests()` instead of maintaining a second executable list.

Historical one-off regression files may remain in the repository for forensic or compatibility purposes, but they are not considered active suite members until deliberately assigned in `test_suites.py`. Active regression coverage validates the canonical materialized/runtime output directly and no longer reads historical patch source merely to prove current product behavior.
