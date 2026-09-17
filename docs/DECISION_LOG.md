# JJ Arena Durable Decision Log

Updated: 2026-09-17

This file records **why durable architectural/product decisions exist**. It is not a changelog and should not duplicate every implementation detail.

## D-001 — Chat history is not the project source of truth

Decision: Long-running ChatGPT conversations are treated as disposable working sessions. Durable project state lives in the repository.

Reason: JJ Arena development spans many long conversations and individual chats can reach their maximum length. Relying on one conversation creates continuity risk and makes old/stale implementation details too easy to treat as current truth.

Consequence: New chats begin from `docs/PROJECT_STATE.md`, current repository/runtime evidence, and a compact handoff when needed.

## D-002 — `materialized_v1244/` remains immutable canonical core

Decision: Ordinary feature, UX, performance, security, or administration work must not directly modify `materialized_v1244/`.

Reason: The materialized v1.24.4 core acts as a validated Golden Master and parity boundary. Direct edits would erase the distinction between known-good core behavior and later integration work.

Consequence: Improvements normally live in root-level integration/extension layers. Historical reconstruction remains available as rollback/parity reference.

## D-003 — Production browser output is built, not rewritten per request

Decision: Browser transforms are compiled into validated output before serving. Request handling does not dynamically rewrite application JS/CSS/HTML.

Reason: Deterministic build ownership is easier to test, faster at runtime, and reduces hidden production behavior.

Consequence: `served_assets.py`, `browser_asset_pipeline.py`, and the validated `.jj_build` output own browser construction. `app.py` owns transport concerns.

## D-004 — One canonical public Ring table

Decision: `jj-table-a` is the canonical public Ring table. Historical table-B behavior remains compatibility/rollback context rather than a public product choice.

Reason: The product was simplified to reduce unnecessary navigation/state complexity while preserving historical compatibility.

Consequence: New UI/product behavior must not casually restore public A/B table selection.

## D-005 — Point ledger is authoritative for official points

Decision: Official point mutations, including quiz rewards, flow through the point ledger.

Reason: Rankings, audits, rewards, and future tournament integrations require one coherent accounting model.

Consequence: Features such as Sit&Go must integrate with the ledger rather than maintain an independent balance system.

## D-006 — Account deletion preserves historical integrity

Decision: Account deletion uses tombstoning rather than destructive row deletion.

Reason: Historical point/ranking/audit records must retain referential integrity and attribution.

Consequence: Deleted accounts are excluded from active management/login surfaces while historical references remain valid.

## D-007 — Runtime performance work must preserve game semantics

Decision: Performance optimization is allowed only when game timing, state privacy, ranking, rake, points, and settlement semantics remain unchanged.

Reason: JJ Arena's expected concurrency is modest; correctness and gameplay fidelity have higher priority than marginal throughput gains.

Consequence: Preserve at least the 45-second action timeout, 1.6-second next-hand delay, staged forced runout timing, immediate WebSocket behavior, and personalized card/state privacy.

## D-008 — Subtractive product design is the default

Decision: JJ Arena should remove or consolidate unnecessary surfaces instead of indefinitely accumulating features.

Reason: The application grew through additive development and reached a point where navigation, maintenance, compatibility, and cognitive load matter as much as feature count.

Consequence: New features require a real current need and lifecycle ownership. Retired surfaces are not revived accidentally.

## D-009 — Sit&Go is a deliberate extension, not a separate platform

Decision: Sit&Go should reuse JJ Arena's existing identity, points, operational conventions, and familiar Ring-style UI patterns where appropriate.

Reason: A separate architecture would duplicate concepts and increase operational complexity.

Consequence: Sit&Go-specific logic may remain modular, but user/account/point integration should stay coherent with the main application.

## How to add entries

Only add an entry when the reasoning is likely to matter after the current chat, PR, or release is forgotten.

Use:

```text
## D-XXX — Short decision title

Decision: ...
Reason: ...
Consequence: ...
```

Do not use this file for ordinary bug fixes, release notes, or temporary TODOs.