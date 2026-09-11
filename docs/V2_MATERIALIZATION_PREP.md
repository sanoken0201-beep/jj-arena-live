# JJ Arena v2 Core — Materialized Runtime Preparation

Status: preparation only. This document does **not** authorize a production runtime switch.

## Golden Master

The v2 migration baseline is the validated `main` commit:

- Commit: `c506ab5305a316bf66aa53b841c3134f8cbfb400`
- Runtime version: `1.24.4`
- Static cache generation: `v56`
- Main GitHub Actions run: `#383` (`success`)

No functional feature work should be mixed into the materialization change.

## Why this migration is required

Production currently reconstructs the application at startup from the v1.4 release bundle and an ordered patch chain. `runtime_builder.py` applies v15 through the v55 family, including compatibility/post/final patches, to create a temporary runtime. `app.py` then imports that reconstructed runtime and installs additional root-level extensions such as admin management, Daily Quiz, hand analytics, learning content, operations hardening, and resilience.

This has been effective for safe incremental recovery, but it is now the wrong long-term base for larger features such as spectator mode, tournament orchestration, multi-level admin roles, and an AI poker coach. The next core release should make the verified final source tree the normal source of truth.

## Migration principle

**Materialize first, refactor later.**

The first v2 core candidate must preserve behavior and data contracts. It must not be a rewrite.

The initial target is equivalent to:

```text
release_v14 + ordered patches + installed extension layer
                         |
                         v
              verified v1.24.4 behavior
                         |
                         v
             ordinary source code tree
```

The migration is successful only when the materialized application passes the same behavior/security tests as the legacy reconstruction path.

## Hard boundaries for the materialization PR

The first materialization PR must not intentionally change:

- PostgreSQL schema or production data
- account IDs, PIN hashes, sessions, or authentication semantics
- roles (`admin` / `member`) or authorization behavior
- official JJ point ledger semantics
- Daily Quiz reward rules (+10 per answered question, existing daily cap/atomicity behavior)
- ranking rules
- Arena chips accounting
- poker hand rules or settlement behavior
- side pots, split pots, short all-ins, minimum raise rules
- No Flop No Drop behavior
- forced all-in runout staging or showdown hold timing
- WebSocket authentication or HTTP fallback behavior
- card privacy rules
- analytics/statistic definitions
- frontend user flows or copy except materialization-specific version metadata if required
- Render database resource

Any required change outside these boundaries must be split into a later PR.

## Current architecture inventory

### Reconstructed core

`runtime_builder.py` owns deterministic reconstruction from:

- `release_v14/`
- `v15_patch.py` ... `v55_patch.py`
- compatibility/post/final patch modules
- `mobile_poker_hotfix.py`

The reconstructed runtime currently contains the core server, database/poker implementation, and player frontend assets.

### Extension layer installed by `app.py`

The root production entrypoint also installs or applies:

- `admin_copy_patch`
- `admin_console`
- `admin_ledger_stabilization`
- `admin_delete`
- `admin_pin_verification`
- `learning_content`
- `daily_quiz`
- `hand_analytics`
- `hand_analytics_hardening`
- `operations_learning`
- `operations_learning_hardening`
- `resilience`
- one-time `online_results_cleanup`
- extension-route prioritization ahead of the SPA catch-all

These must be explicitly accounted for when moving from a reconstructed runtime to a normal package. Merely copying `/tmp/jj_arena_v56_runtime` is not the complete v2 migration.

## Phase plan

### Phase 0 — Freeze and inventory

1. Freeze `c506ab5` as the Golden Master.
2. Keep v1.24.4 behavior frozen while the core migration is prepared.
3. Generate deterministic manifests of the reconstructed runtime.
4. Record all externally visible routes and all database tables/columns used by the extension layer.
5. Preserve the existing full CI suite.

### Phase 1 — Materialize the reconstructed core

1. Generate the exact v1.24.4 reconstructed runtime into a candidate source directory.
2. Exclude runtime state (`*.db`, SQLite WAL/SHM, caches, `__pycache__`, `*.pyc`).
3. Commit source/static assets as ordinary files.
4. Do not yet restructure modules or rename public APIs.
5. Keep the legacy builder available as a parity oracle.

### Phase 2 — Attach the extension layer without behavior changes

1. Replace dynamic `sys.path` injection with normal imports.
2. Install the same extension routes in the same effective order.
3. Preserve the SPA catch-all ordering contract.
4. Preserve one-time cleanup/migration guards.
5. Verify both SQLite and PostgreSQL paths.

### Phase 3 — Dual-path parity gate

For the duration of the migration, CI must be able to build both:

- legacy reconstructed v1.24.4
- materialized v2 candidate

The following parity gates are mandatory:

| Area | Required gate |
| --- | --- |
| Core files | deterministic manifest / expected source set |
| HTTP | route inventory and status/response contract tests |
| Auth | login, session, role checks, admin recovery |
| WebSocket | authenticated connection and reconnect behavior |
| Poker | engine integration, legal actions, settlement, side pots, split pots |
| Safety | card privacy, non-turn rejection, action idempotency |
| Mobile/Desktop UI | existing Chromium regression suite |
| Quiz | SQLite + PostgreSQL concurrency, rollover, reward atomicity |
| Analytics | SQLite + PostgreSQL integration and statistic definitions |
| Admin | account deletion/disable/recovery and point-ledger operations |
| Database | no destructive schema migration; same production DB remains usable by rollback |

### Phase 4 — Production cutover

Only after all parity gates pass:

1. Deploy materialized code while keeping the existing PostgreSQL database.
2. Verify `/api/health`, login, Home, Ranking, Quiz, Analysis, Admin, and a real poker table.
3. Verify WebSocket synchronization on at least two clients.
4. Keep the last v1.24.4 commit as immediate rollback target.
5. Do not delete legacy reconstruction files in the cutover PR.

### Phase 5 — Cleanup after stable production verification

Only after the materialized runtime has been stable in production:

- archive/remove release bundle and old patch-chain files
- rename version-specific smoke tests into feature-oriented tests
- reorganize code into stable packages (`auth`, `poker`, `quiz`, `analytics`, `admin`, etc.)
- remove compatibility shims that are demonstrably unreachable

This phase must be independent from the cutover itself.

## Database rule

The production database is a compatibility boundary, not a migration workspace.

For the materialization release:

- no new PostgreSQL instance
- no reset/reseed
- no destructive `ALTER`/`DROP`
- no direct point-history rewriting
- no account/session identifier regeneration

The old v1.24.4 code must remain capable of reconnecting to the same database after rollback.

## Legacy retention / rollback

Do not delete `release_v14`, `runtime_builder.py`, or patch modules during the first v2 cutover. They remain the reconstruction oracle and rollback reference until v2 has been verified in production.

## Acceptance criteria for "v2 Core ready"

The v2 Core migration is ready to merge only when all are true:

- legacy Golden Master can still be reconstructed
- materialized candidate starts without applying the historical patch chain
- all existing CI behavior/security tests pass against the candidate
- SQLite and PostgreSQL 18 test paths pass
- browser layout regressions pass at existing desktop/mobile sizes
- no production DB migration is required for cutover
- Render can start the materialized entrypoint directly
- rollback to `c506ab5` remains possible without DB repair
- a documented production verification checklist exists

## Feature order after v2 Core

After the core has been materialized and verified, planned major work proceeds in this order:

1. admin roles / security model
2. spectator mode
3. online Sit & Go / MTT orchestration
4. data-grounded AI Poker Coach

This ordering intentionally establishes authorization and observation boundaries before tournament orchestration and AI access to private hand data.
