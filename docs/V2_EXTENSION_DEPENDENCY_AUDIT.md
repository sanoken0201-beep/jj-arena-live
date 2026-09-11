# JJ Arena v2 — Dynamic Extension Dependency Audit

This audit records behavior that is **not** captured by merely copying the reconstructed `/tmp/jj_arena_v56_runtime` tree.

## Critical finding

The production application is a two-layer system:

1. `runtime_builder.py` reconstructs the v1.24.4 core runtime.
2. root-level modules imported by `app.py` mutate/install behavior on top of that runtime.

Therefore a safe v2 materialization cannot stop after copying the reconstructed core files.

## Mutation / installation points

### `app.py`

Production startup currently:

- reconstructs the runtime
- places the runtime directory at the front of `sys.path`
- imports reconstructed `server`, `app`, and `db`
- applies the online-results one-time migration
- installs admin, quiz, learning, analytics, operations and resilience extensions
- reorders extension/API routes ahead of the reconstructed SPA catch-all

The effective route ordering is part of current behavior and must be preserved until explicitly refactored later.

### `hand_analytics_hardening.py`

This is an actual module monkey-patch layer. `install()` replaces:

- `analytics._compute_flags`
- `analytics._record_action`

It also inspects the server-authoritative action deadline to synchronize analytics decision-time semantics.

**v2 implication:** these final semantics must be folded into the materialized analytics implementation (or installed through an explicit adapter) before the hardening shim can be removed.

### `operations_learning_hardening.py`

`apply()` replaces functions on the already-loaded operations module:

- `learning_payload`
- `_quiz_anomalies`
- `operations_payload`

**v2 implication:** the final functions after hardening are the behavioral baseline, not the pre-hardening module definitions.

### `resilience.py`

`install()` has several startup/runtime side effects:

- creates `ops_error_log`
- creates `table_state_backups`
- restores invalid table state from backups on startup
- wraps `server.save_table` so every save attempts a backup
- installs HTTP error-capture middleware
- installs resilience/admin backup routes

**v2 implication:** import/installation order is security and durability relevant. A materialized server that starts before this layer is attached is not equivalent to current production.

### `online_results_cleanup.py`

`apply()` is a guarded one-time data migration keyed by:

`2026-09-10-clear-existing-online-results`

It creates/uses `app_migrations` and, only on first application, deletes old `online_hand_results` rows.

**v2 implication:** the existing migration marker must remain recognized. The v2 migration must never re-key or replay this cleanup.

## Main migration risks

| Risk | Impact | Required control |
| --- | --- | --- |
| Copy only reconstructed core | Missing Quiz/Admin/Analytics/Resilience behavior | extension parity inventory + startup test |
| Remove hardening shims too early | statistic/learning semantics regress | fold final wrapped behavior first |
| Change startup order | route shadowing or missing durability wrapper | explicit app factory / deterministic install order |
| Run migration against wrong DB | destructive historical result cleanup | preserve existing migration key and isolated CI DB |
| Import app in tests with production `DATABASE_URL` | accidental production mutation | force isolated SQLite/PostgreSQL test DB |
| Refactor while materializing | parity failures hard to localize | no feature/refactor work in cutover PR |
| Remove legacy patch chain at cutover | loses rollback/parity oracle | retain until post-cutover cleanup |

## Recommended v2 application-factory target

The first clean architecture should make installation order explicit rather than relying on import side effects. Example conceptual order:

```text
create_app()
  -> create/load database adapter
  -> install core auth/routes
  -> install poker routes/websocket
  -> install quiz
  -> install analytics + final statistic semantics
  -> install learning/operations
  -> install admin
  -> install resilience wrappers/middleware
  -> validate route order
  -> return app
```

This is a later refactor target. The first materialized candidate should preserve current behavior before moving to this structure.

## Pre-cutover evidence still required

Before the production switch, collect and compare:

1. complete FastAPI HTTP route inventory (method + path)
2. WebSocket route inventory
3. SQLite schema after fresh isolated startup
4. PostgreSQL 18 schema after fresh isolated startup
5. startup-time migration markers
6. middleware ordering
7. functions currently wrapped/replaced by hardening modules
8. table-state persistence/backup behavior

These artifacts should be generated from isolated test databases only.
