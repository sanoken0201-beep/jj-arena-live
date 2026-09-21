# JJ Arena — Decision Log

Updated: 2026-09-21

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

The entry fee is debited at registration as `sitngo_entry` and paired with a `sitngo_payments` escrow record. Registration is allowed even when the current official point balance is lower than the fee, so a member's season balance may become negative. A pre-start cancellation, administrator cancellation, or minimum-player cancellation returns that exact recorded amount once as `sitngo_refund`; refunds reference the original debit and use a database-level claim for idempotency.

Registration is also the seating commitment. Once registered, the entrant is reserved against other poker-table membership and is seated into the Sit&Go at start whether or not they reconnect or open the tournament table. While absent, scheduled blinds/BBA continue to post and unattended actions use the normal tournament timeout check/fold behavior.

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

Historical release bundles and patch modules are not runtime dependencies and must not be silently reintroduced into the compatibility builder. Stage 7B.2 removes the remaining `release_v14/`, `v18_assets/`, and `v54_patch.py` working-tree artifacts; forensic access is through Git history. `smoke_test_runtime_builder_snapshot.py`, `smoke_test_legacy_artifacts_pruned.py`, and the production release gate protect this contract.

## D-012 — Sit&Go blind progression is hand-count based and online chips remain exact

**Date:** 2026-09-21  
**Status:** Accepted

New Sit&Go tournaments advance one blind level after every 12 completed hands, only between hands. Persisted minute, target-minute and prepared-minute values remain compatibility/rollback metadata and do not select the active blind level.

Tournament chips use a permanent exact 100-point accounting unit. Physical-tournament color-up behavior must not round, race off or redistribute value between online players. The legacy color-up compatibility hook may only normalize old persisted state without changing player stacks. BBA is dead money in the main pot and browser POT calculation must include it exactly once.

## D-013 — A running Sit&Go must not hide the next registration event

**Date:** 2026-09-21  
**Status:** Accepted

JJ Arena continues to run at most one Sit&Go table at a time. When another event is scheduled, accepting registrations or waiting in `starting`, the player lobby may show that upcoming event alongside the currently running tournament. This prevents a live tournament from hiding an open registration window while preserving the single-running-table operational contract.

## D-014 — Sit&Go safety telemetry is aggregate and privacy-preserving

**Date:** 2026-09-21  
**Status:** Accepted

Runtime observability for Sit&Go action safety stores only daily aggregate counters for missing tokens, duplicate actions, stale hand/turn submissions, late actions, timeout-boundary protection, automatic timeout actions and restart recovery. It must not persist user identity, event/table IDs, hand IDs, cards, chip amounts, network identifiers, session identifiers or free-form text.

Observability failure must never block or alter tournament actions, timeout progression or settlement.

## D-015 — Ring UX recovery telemetry stays batched, aggregate and identity-free

**Date:** 2026-09-21  
**Status:** Accepted

Operational UX measurement may distinguish a WebSocket connection opening from successful recovery to a fresh authoritative table state, measure same-page seat-to-READY latency, count final action submission failures, and count table-to-review opens plus review-later bookmarks.

These measurements must reuse the existing batched telemetry sender. They must not introduce polling or a background database reader, and must not persist user/account identity, table or hand IDs, cards, chip/bet amounts, chat, IP address, user agent, session ID or free text. Raw UX-event retention remains 30 days. Browser instrumentation is compiled as the final append-only stage after runtime browser consolidation.

## D-016 — Rake audit health separates current integrity from historical defects

**Date:** 2026-09-21  
**Status:** Accepted

The production rake audit keeps all-time `hand_conservation_or_completeness` and `rake_formula_violation` counters for compatibility and forensic investigation. It also classifies those findings into `current_*` and `legacy_*` buckets using the corrected-policy boundary.

The operational `status` and `current_anomaly_total` must be computed from current-period and structural checks only. Known legacy defects remain visible in the report but must not independently mark the corrected current system unhealthy. The audit remains read-only and does not rewrite historical data.

## D-017 — Sit&Go operator alerts are conservative and local

**Date:** 2026-09-21  
**Status:** Accepted

Sit&Go runtime safety counters may produce administrator warnings, but alerting must not treat normal poker behavior as an incident. Player action deadline expiry and the resulting automatic check/fold are excluded from operator alerts. Missing action tokens, repeated stale hand/turn submissions and tournament restart recovery are actionable signals; duplicate retries and protected timeout-boundary races are informational unless future evidence justifies stronger treatment.

Alert derivation is server-owned so browser and future notification channels share one policy. The current notification surface is the authenticated administrator console only. No external provider receives telemetry until a separate integration is explicitly selected and reviewed.

## D-018 — Sit&Go production is single-worker and snapshot-backed

**Date:** 2026-09-21  
**Status:** Accepted

JJ Arena's table locks, WebSocket connection hub and Sit&Go scheduler ownership are process-local. Production therefore runs exactly one ASGI worker. The Render start command and `WEB_CONCURRENCY` both pin one worker, while startup rejects an explicitly conflicting worker-count environment rather than silently running an unsafe multi-process topology.

The authoritative Sit&Go state remains `sitngo_games.state_json`. In addition to normal persisted restart recovery, the runtime keeps up to 40 meaningful same-event generations in `sitngo_state_backups`. Revision and elapsed-clock heartbeat changes alone do not create new generations. Backup writes are fail-open so observability/recovery storage cannot block poker actions. If the current state is malformed or structurally invalid, restoration is fail-closed and may use only a validated same-event snapshot with a matching stored revision.

## D-019 — Sit&Go timing metadata is compatibility-only and browser transforms have one owner

**Date:** 2026-09-21  
**Status:** Accepted

Sit&Go blind progression is determined only by completed hand count. The per-level `minutes` field remains in persisted/API structures for schema and rollback compatibility, but new create/update writes canonicalize it to 10 so direct or stale clients cannot create a second ineffective timing contract. Historical stored minute values remain readable and do not affect blind selection.

Player Sit&Go browser transforms are owned by the dependency-free `sitngo_browser_config.py` and installed explicitly by the production asset compiler before transform aliases are bound. Runtime extension modules may delegate to that owner but must not carry parallel UI mutation implementations. The committed `admin_static` files are the administrator UI source of truth and must not be rewritten at application startup.

## D-020 — Sit&Go adopted contracts require explicit regression traceability

**Date:** 2026-09-21  
**Status:** Accepted

The production Sit&Go contract is broader than any single smoke test. `sitngo_acceptance.py` is the machine-readable traceability map from each adopted contract area to active Sit&Go regression evidence. The manifest does not replace behavioral tests; it prevents coverage ownership from drifting silently as tests are consolidated, renamed, added, or retired. A release-gated regression requires every active Sit&Go behavioral test to appear in that map, while browser-only evidence remains GitHub-only rather than entering Render's dependency-light release gate.

## D-021 — Account deletion expires official points without erasing audit history

**Date:** 2026-09-21  
**Status:** Accepted

A deleted member account no longer contributes to official JJ rankings. Point-ledger transactions and online-hand results remain stored for auditability, but rows tied to the deleted user ID are excluded from ranking aggregation rather than being destructively rewritten.

Physical club entries are historically keyed by ranking name rather than user ID. Once an account generation for that ranking name is deleted, those name-keyed points are retired with it. A later same-name registration starts a new generation after the deletion boundary and must not inherit the deleted account's club, online or ledger points.

This rule applies to accounts that were already tombstoned before the rule was introduced as well as future deletions. Raw records remain available for forensic review; point expiry is an aggregation rule, not data destruction.

## D-022 — Poker decisions use three mandatory 30-second timebank cards

**Date:** 2026-09-21  
**Status:** Accepted

Every Ring and Sit&Go decision receives a 30-second base action window. Each participant receives three timebank cards for the duration of that seating/tournament participation. When a decision deadline expires, a remaining card is consumed automatically and grants exactly 30 more seconds; players cannot choose to preserve a card by declining its use. Cards persist across hands and are not replenished until a new participation begins.

When no cards remain, expiry of the 30-second decision window forces a fold even if check is a legal poker action. Timeout settlement remains server-owned, and Sit&Go boundary protection for an action received before the deadline continues to take precedence over automatic timeout settlement.
