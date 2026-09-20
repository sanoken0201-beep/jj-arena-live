# JJ Arena — Decision Log

Updated: 2026-09-20

This file records durable project decisions and the reason behind them. It is not a chronological transcript of every change.

Use an entry when future developers or AI agents would otherwise be tempted to undo or reinterpret a deliberate choice. Current behavior belongs in `PROJECT_STATE.md`; operational procedures belong in `OPERATIONS.md`.

## D-001 — GitHub is the durable project memory

**Date:** 2026-09-17  
**Status:** Accepted

JJ Arena development spans many long ChatGPT conversations, and individual chats can reach their length limit. Chat history is therefore not a reliable system of record.

Durable current state, design decisions and handoff instructions must live in the repository. ChatGPT sessions are disposable workspaces. Before a session is archived or deleted, any decision or requirement that must survive it must be promoted into code, tests or repository documentation.

Conflict resolution follows `PROJECT_STATE.md`: current code/verified production outrank old chat history.

## D-002 — `materialized_v1244` remains immutable for ordinary work

**Date:** 2026-09-17  
**Status:** Accepted

The verified v1.24.4 Golden Master is retained as a stable canonical core. Ordinary product improvements are implemented through root-level extensions, integrations and deterministic browser build stages rather than direct edits to the materialized core.

This keeps parity, rollback and regression reasoning tractable while the application continues to evolve.

## D-003 — Production browser assets are build artifacts, not request-time mutations

**Date:** 2026-09-17  
**Status:** Accepted

Browser transformations are compiled during the build into `.jj_build/`. Production request handling serves the validated result and must not reconstruct or mutate source assets on every request.

The ordering of final browser stages belongs in `browser_asset_pipeline.py`. This reduces runtime complexity and makes the browser output reproducible and testable.

## D-004 — Compatibility code is not automatically an active product surface

**Date:** 2026-09-17  
**Status:** Accepted

Historical routes, table data, patch modules and rollback paths may remain because stale clients, stored data, parity checks or rollback procedures still depend on them. Their presence in the repository does not authorize new product behavior to be built on them.

`feature_lifecycle.py` and `ARCHITECTURE_STATUS.md` define active, compatibility-only and retired surfaces. Re-promoting a retired or compatibility-only surface requires an explicit reviewed product decision.

## D-005 — One canonical public Ring table

**Date:** 2026-09-17  
**Status:** Accepted

The public Ring experience exposes `jj-table-a`. Historical table B is retained only for compatibility/rollback data and must not reappear in the public table list without a deliberate product change.

The reason is subtractive product design: a single canonical table reduces duplicate navigation, ambiguous state and unnecessary operational surface for the expected club-scale concurrency.

## D-006 — Production changes follow protected-branch release order

**Date:** 2026-09-17  
**Status:** Accepted

Normal production work follows:

`branch -> PR -> required CI -> main -> Render checksPass deploy -> production verification`

Direct changes that bypass required checks are not the normal operating model. Documentation-only changes should follow the same workflow when practical so the process remains habitual and auditable.

## D-007 — Official JJ points use ledger semantics

**Date:** 2026-09-17  
**Status:** Accepted

Official points are treated as an auditable ledger, not as a mutable display balance. Earning, spending, prizes, reversals and refunds should be represented through ledger-backed operations with precision and ranking behavior covered by regression tests.

Practice poker chips remain a separate accounting domain unless an explicit feature defines a point-ledger transaction.

## D-008 — Sit&Go remains isolated from Ring gameplay state

**Date:** 2026-09-17  
**Status:** Accepted

Sit&Go uses dedicated modules and persistence so tournament-specific ante, blind progression, tournament chips and lifecycle rules do not alter Ring engine globals or Ring settlement.

The Ring renderer and interaction patterns may be reused for UX consistency, but tournament state and cash/practice-chip settlement remain separated.

## D-009 — Sit&Go entry and prize points use locked ledger escrow

**Date:** 2026-09-20  
**Status:** Accepted

Sit&Go entry fees and prizes are part of the official JJ-point ledger, while tournament chips remain isolated gameplay units.

The administrator chooses the entry fee and field-size payout percentages before registration. Defaults are winner-takes-all for 2–5 entrants and 70% / 30% for 6 entrants. The first registration locks the point terms so participants cannot be charged under one rule and paid under another.

The entry fee is debited at registration as `sitngo_entry` and paired with a `sitngo_payments` escrow record. A pre-start cancellation, administrator cancellation, or minimum-player cancellation returns that exact recorded amount once as `sitngo_refund`; refunds reference the original debit and use a database-level claim for idempotency. Insufficient balances fail before registration commits.

Before the first hand, paid events fail closed unless the registered participant set exactly matches unrefunded escrow, each payment uses the locked fee, and its referenced `sitngo_entry` ledger row matches user and amount. Persisted payout JSON is revalidated at read/start/settlement time. Free events likewise refuse to start if unexpected active escrow exists.

At tournament completion, the entire recorded pool is allocated in integer hundredths and written as `sitngo_prize` rows plus one `sitngo_settlements` record. Settlement is idempotent and re-verifies persisted awards against escrow and prize ledger on replay. Tied places split the occupied prize slots; any indivisible 0.01 pt residual is assigned by randomized seat order, with user ID only as a deterministic fallback. The general admin reversal path cannot reverse tournament accounting rows independently.

## D-010 — Long ChatGPT chats are expected; continuity is document-driven

**Date:** 2026-09-17  
**Status:** Accepted

Avoiding long development chats is not a project goal. Complex implementation sessions may naturally become large and may eventually reach ChatGPT limits.

Continuity is achieved by updating the canonical project state and decision log and producing a compact handoff, not by copying the entire conversation into the next chat. This makes old chats optional historical material rather than a runtime dependency for future development.

## D-011 — Compatibility rollback runtime is built from the verified materialized snapshot

**Date:** 2026-09-17  
**Status:** Accepted

The compatibility/parity runtime must not reconstruct v1.24.4 by unpacking `release_v14` and replaying the historical v15–v55 patch chain.

`runtime_builder.py` copies the files recorded in `materialized_v1244.manifest.json` into an isolated runtime directory and verifies their size/hash before and after copying. This makes the committed `materialized_v1244/` tree the single canonical v1.24.4 source for both production loading and compatibility construction.

Historical release bundles and patch modules may remain for forensic history, but they are not runtime dependencies and must not be silently reintroduced into the compatibility builder. `smoke_test_runtime_builder_snapshot.py` and the production release gate protect this contract.