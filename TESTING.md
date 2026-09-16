# JJ Arena Test Structure

Tests are organized by supported product surface rather than by the historical patch/phase that introduced them. The machine-readable catalog is `test_catalog.py`.

## Suites

- **auth-security** — PIN authentication, cookie/session boundary, WebSocket auth, public gateway Origin checks, canonical admin user API.
- **points-integrity** — exact point ledger, reversal safety, export safety, duplicate-submit protection.
- **frontend-contract** — prebuilt asset integrity, PWA update behavior, canonical frontend pipeline, feature lifecycle and copy labels.
- **ring-gameplay** — core NLH behavior, one-public-table contract, runtime performance/observability and retention.
- **production-architecture** — immutable materialized core, production entrypoint isolation and v2 cutover invariants.
- **sitngo** — Sit&Go scheduling/gameplay tests. Kept separate from ring and club point-entry semantics.

Real-browser tests remain GitHub-only because Render's production build should not install browser tooling. `production_release_gate.py` imports its Render-safe critical list from `test_catalog.PRODUCTION_RELEASE_TESTS`.

## Branch protection

Existing required GitHub check names remain stable (`production release gate`, `phase4b`, `auth-security`, `point-ledger-precision`). Historical job names are compatibility labels for branch protection; they do not define architectural ownership.

## New regression rule

A new bug fix should be added to the suite that owns the affected product behavior, not to a new one-off historical phase. New standalone workflows should be avoided unless they require a materially different environment such as a real browser or disposable PostgreSQL.
