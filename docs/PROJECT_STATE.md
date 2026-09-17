# JJ Arena Canonical Project State

Updated: 2026-09-17
Status: Canonical handoff source for future ChatGPT/development sessions

## Purpose

This file is the compact source of truth for **the current JJ Arena project state**. It exists so development can continue safely even when individual ChatGPT conversations become too long, are archived, or are deleted.

Rules:
- Prefer current repository/runtime evidence over old chat history.
- Keep this file focused on **what is true now**, not the full historical story.
- Record the reason behind durable design decisions in `docs/DECISION_LOG.md`.
- Use `docs/CHAT_HANDOFF_TEMPLATE.md` when moving work to a new chat.
- If this file conflicts with production code, verified production behavior, or `OPERATIONS.md`, investigate and update this file rather than blindly following stale text.

## Repository and production

- Repository: `sanoken0201-beep/jj-arena-live`
- Production branch: `main`
- ASGI entrypoint: `app:app`
- Primary production service: `jj-arena-live`
- Production database: existing Render PostgreSQL `jj-arena-db`
- Region: Singapore
- Canonical operational procedure: `OPERATIONS.md`
- Detailed production-surface classification: `ARCHITECTURE_STATUS.md`

`jj-arena-club` is legacy/public-proxy history and must not be treated as the canonical development target unless `OPERATIONS.md` is deliberately changed.

## Canonical application architecture

- Immutable canonical core: `materialized_v1244/`
- Production integration path: `app_materialized.py` + root-level extension/integration modules + `app.py`
- Historical rollback/parity reference: `app_legacy.py` + historical reconstruction path
- `materialized_v1244/` is **not an ordinary edit target**.
- New product behavior, security, performance, admin, analysis, learning, and UX integration should normally be implemented outside the immutable core.

### Browser build

- Base browser input originates from `materialized_v1244/static`.
- `served_assets.py` compiles the validated browser assets.
- `browser_asset_pipeline.py` is the explicit post-build orchestration point.
- `.jj_build` is the canonical validated browser output.
- `app.py` may perform transport work such as caching/compression/ETag handling, but should not mutate browser source at request time.

## Active product areas

Current active areas include:
- PIN-based authentication and session handling
- canonical `/admin` administration UI
- official point ledger and ranking integration
- one public Ring table: `jj-table-a`
- online poker state/action/WebSocket flow
- Poker Lab / hand analysis and review
- announcements and home/ranking surfaces
- daily quiz and point reward flow
- Sit&Go through its root-level integration/data model

For lifecycle classification of active, compatibility-only, and retired surfaces, use `ARCHITECTURE_STATUS.md`.

## Data integrity invariants

These are not optional implementation details:
- Official points flow through the point ledger.
- Quiz rewards flow through the point ledger.
- Duplicate reward for the same quiz attempt is forbidden.
- Ranking/point/rake/hand-settlement semantics must not be changed as a performance optimization.
- Production PostgreSQL must not be replaced by SQLite.
- Account deletion is tombstone-based so historical point/ranking/audit references remain valid.
- Destructive production-schema rollback is not the normal rollback strategy.

## Online poker invariants

Changes should keep poker-engine, API/WebSocket, UI, and runtime-performance concerns separated whenever practical.

Runtime/performance changes must preserve at minimum:
- 45-second action timeout
- 1.6-second next-hand delay
- staged forced-runout timing
- immediate WebSocket behavior
- personalized state/card privacy
- ranking/rake/point semantics

Game-rule changes require regression coverage for minimum raise, short all-in, side pots, split pots, turn ownership, and timeout behavior.

## Security invariants

- No plaintext PIN/password/database credentials in source or logs.
- PINs remain one-way hashed.
- Admin role checks remain mandatory for admin APIs.
- Production session cookies retain secure attributes.
- WebSocket authentication uses the existing same-origin session cookie; credentials do not belong in WebSocket query strings.
- Credential/session changes must invalidate affected sessions appropriately.
- Recovery credentials must not remain permanently configured.

## Test and release ownership

- `test_suites.py` owns active regression grouping.
- Production release selection is consumed by `production_release_gate.py`.
- Active suites include auth/security, points integrity, ring gameplay, browser contract, runtime release, and Sit&Go.
- Browser-only tests must not be accidentally treated as Render production-gate tests.
- Historical one-off tests may remain for forensic value but are not active unless deliberately assigned.

Normal release flow remains: branch from known-good `main` -> focused changes -> regression coverage -> CI -> merge to `main` -> verify Render deployed the intended SHA -> production smoke checks.

## Current development direction

JJ Arena has reached a stage where **subtractive design matters**. New features should not be added merely because they are possible. Before adding a product surface:
1. confirm it solves a current user/operations need;
2. check whether an existing surface can absorb the function;
3. preserve clear lifecycle ownership;
4. avoid reviving retired/compatibility-only behavior accidentally.

Sit&Go is an intentional addition and should remain integrated with the existing point system and familiar Ring-style operational UI rather than becoming an isolated product architecture.

## Chat/session operating model

ChatGPT conversations are **working sessions, not the authoritative project archive**.

When starting a new JJ Arena chat:
1. read `docs/PROJECT_STATE.md`;
2. read the relevant sections of `OPERATIONS.md` and `ARCHITECTURE_STATUS.md`;
3. inspect current `main` / relevant PR / Render state rather than trusting old chat statements;
4. read the latest handoff from the previous chat if one exists;
5. perform the requested work;
6. update canonical documentation when a durable project fact changes.

When a chat approaches its limit, create a handoff using `docs/CHAT_HANDOFF_TEMPLATE.md`. The next chat should not need the full old conversation.

## What should NOT be copied into this file

Do not accumulate:
- every historical version number;
- every failed experiment;
- solved transient bugs;
- obsolete implementation details;
- large diffs or CI logs;
- speculative feature ideas that were never adopted.

Those belong in Git history, issues/PRs, temporary handoffs, or `docs/DECISION_LOG.md` only when the reasoning remains important.

## Documents and precedence

Use this order when resolving uncertainty:
1. verified current production behavior and current code/configuration;
2. `OPERATIONS.md` for production operations and safety procedure;
3. `ARCHITECTURE_STATUS.md` for current surface/lifecycle architecture;
4. `docs/PROJECT_STATE.md` for compact cross-chat state;
5. `docs/DECISION_LOG.md` for durable rationale;
6. latest chat handoff for unfinished work;
7. old chat history only as forensic context.

If a lower-precedence source conflicts with a higher-precedence source, do not silently merge the two. Verify the current system and update stale documentation.