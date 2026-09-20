# JJ Arena — Canonical Project State

Updated: 2026-09-21
Snapshot basis: Stage 6 / Stage 7B.2 / Sit&Go legacy-source / architecture-test cleanup completion based on `main` at `21a3551296304f18250c9f2c0015d98b2fa71782`

This file is the **human/AI handoff source of truth for the current project state**. It exists so long ChatGPT development chats can be replaced without losing critical context.

The commit above is only the snapshot used to write this document. At the start of every new work session, inspect the current `main` branch first and treat newer repository state as authoritative.

## 1. Source-of-truth order

When sources conflict, use this order:

1. Current `main` code, tests, schema and deployment configuration.
2. Current production state verified from Render/PostgreSQL where the task depends on production.
3. This `PROJECT_STATE.md` plus `ARCHITECTURE_STATUS.md` and `OPERATIONS.md`.
4. `DECISION_LOG.md` for the reason behind durable design choices.
5. The latest chat handoff.
6. Old ChatGPT conversations, old audit reports and historical changelogs.

A ChatGPT conversation is a **work session, not durable project storage**. If a chat contains a decision or requirement that must survive deletion of that chat, promote it into the repository documentation or the implementation before ending the session.

If this file conflicts with current code or verified production, do not preserve the conflict for compatibility with a chat. Verify the current behavior and update this file in the same change when practical.

## 2. Repository and release path

Repository: `sanoken0201-beep/jj-arena-live`

Production branch: `main`.

`main` is protected. The required checks currently include:

- `production release gate`
- `phase4b`
- `auth-security`
- `point-ledger-precision`

Normal release order is:

`branch -> PR -> required CI -> main -> Render checksPass deploy -> production verification`

Do not intentionally bypass this order for normal product work.

## 3. Production architecture

Primary Render web service: `jj-arena-live`, Singapore region, 0.5 CPU / 512 MB according to `render.yaml`.

Production ASGI entrypoint:

```bash
python -m uvicorn app:app --host 0.0.0.0 --port $PORT --workers 1
```

Health check: `/api/health`.

Production is intentionally single-worker. `render.yaml` pins both `--workers 1` and `WEB_CONCURRENCY=1`, and startup rejects an explicitly conflicting worker-count environment. The in-process table locks, WebSocket hub and Sit&Go lifecycle owner must not be split across ASGI workers.

Production database: the existing Render PostgreSQL database `jj-arena-db`. Do not create a replacement database during ordinary releases and do not perform destructive migration casually.

`jj-arena-club` is a legacy proxy/compatibility path rather than the target for new implementation work. New product behavior should target `jj-arena-live` unless an explicit architecture decision changes that.

## 4. Immutable core and extension model

`materialized_v1244/` is the canonical v1.24.4 Golden Master and is **immutable for ordinary improvements**.

Normal product changes belong in root-level extensions, integration shims, browser transforms or dedicated modules. Do not edit `materialized_v1244/` merely because it is convenient.

`app_materialized.py` loads the materialized core and applies root-level extensions. `app.py` is the stable Render-facing entrypoint.

`app_legacy.py` remains an isolated parity/emergency-rollback oracle rather than a production import path. `runtime_builder.py` constructs that compatibility runtime by copying only files recorded in `materialized_v1244.manifest.json` and verifying their size/hash. Stage 7B.2 removes the unused `release_v14/`, `v18_assets/`, and `v54_patch.py` working-tree artifacts; historical reconstruction remains available through Git history and is not a runtime dependency.

Do not mix poker game-rule changes and UI-only changes in one patch unless the coupling is unavoidable and explicitly justified.

## 5. Browser asset ownership

`materialized_v1244/static` is immutable input.

`served_assets.py` and the production browser pipeline compile the final browser output into `.jj_build/` during build. `browser_asset_pipeline.py` owns final post-build ordering, and `browser_runtime_consolidation.py` keeps deterministic browser mutation out of request-time serving.

Production should serve validated prebuilt assets rather than execute the historical UX transform chain on each request. Missing production build artifacts should fail closed rather than silently create a different runtime. `served_assets.py` is the single owner of dependency-free browser-transform initialization, including the Sit&Go browser contract installer; `build_served_assets.py` is limited to build → finalize → validate orchestration and must not initialize individual transforms. Sit&Go player browser transforms are configured solely through the dependency-free `sitngo_browser_config.py` before build aliases bind; `sitngo_admin_config.py`, `sitngo_hand_levels.py` and `sitngo_asset_cache.py` no longer maintain parallel player-UI mutation implementations. The committed `admin_static` files are the admin Sit&Go UI source of truth and are never rewritten at process startup.

## 6. Product lifecycle

`feature_lifecycle.py` is the machine-readable lifecycle classification. `ARCHITECTURE_STATUS.md` is the readable architecture summary.

Current active surfaces include authentication, the canonical admin console, official points/ranking integration, the public Ring experience, Poker Lab/hand review, announcements and Sit&Go integration.

Compatibility-only or retired surfaces must not become targets for new product behavior unless their lifecycle classification is deliberately changed in the same reviewed release.

The current public Ring surface is **one table, `jj-table-a`**. Historical table B is compatibility-only and must not be re-exposed by accident.

## 7. Authentication and security invariants

Current member authentication is display name + 6-digit PIN.

Security characteristics include PBKDF2-SHA256 PIN hashing, Admin/Member roles, HttpOnly sessions, production `__Host-` session cookie behavior, rate limiting, same-origin / Fetch Metadata CSRF protection, WebSocket authentication and card-privacy checks.

Legacy Email + Password authentication is retired.

Never place admin PINs, credentials, secrets or production session material in GitHub, ChatGPT handoff documents, logs or commit messages.

## 8. Official points and ranking invariants

Official JJ points are an auditable ledger-backed system. Do not directly overwrite point history as a shortcut.

Point-ledger precision and ranking mapping are regression-protected. Changes to point earning, spending, reversal or settlement must preserve auditability and be tested against PostgreSQL behavior.

Poker practice chips and official JJ points are separate accounting domains unless a feature explicitly defines a ledger transaction between them.

## 9. Ring poker invariants

The Ring game uses server-authoritative state and supports standard NLH actions including minimum raise, short all-in, side pots and split pots.

Operational timing that must not be casually changed:

- 45-second player action deadline.
- At least 1.6-second next-hand/showdown transition behavior where required by the canonical flow.
- Event-driven timeout, forced runout and next-hand progression.
- WebSocket-first synchronization with HTTP fallback/recovery.

Performance work must not trade away action correctness, timing correctness, card privacy, ranking precision or user-visible immediacy.

Production rake integrity auditing retains all-time anomaly counters for forensic investigation but separates corrected-period `current_*` counters from legacy findings. The top-level audit `status` and `current_anomaly_total` are based on current/structural checks rather than known historical defects, so legacy anomalies remain visible without making a corrected current system appear unhealthy.

Ring UX telemetry remains privacy-preserving and low overhead. The existing batched client now distinguishes WebSocket-open events from actual recovery to a fresh authoritative state, measures same-page seat-to-READY latency, counts final action submission failures, and counts table-to-review opens plus review-later bookmarks. It adds no polling loop or background database reader and stores no user/account identity, table/hand ID, cards, chip/bet amount, chat, IP, user agent, session ID or free text. Raw UX events retain the existing 30-day limit. The admin UX dashboard exposes these aggregate KPIs.

## 10. Sit&Go current implementation

Sit&Go is a dedicated root-level subsystem (`sitngo.py`, `sitngo_runtime.py`, `sitngo_ui.py`, `sitngo_points.py`) with its own persistence and tests. New events default to 30,000 tournament chips and a big-blind-ante structure. Administrators may configure the starting stack and each level's SB/BB/BBA before play begins. New tournaments advance one level after every 12 completed hands; persisted minute/target/prepared-minute fields are legacy/rollback metadata and do not select blinds. New create/update API writes canonicalize each level's compatibility `minutes` value to 10, while historical persisted values remain readable for rollback compatibility. Online tournament accounting stays in an exact permanent 100-point unit and does not redistribute stacks through physical-style color-ups. Tournament chips remain isolated from Ring settlement.

Official JJ points are integrated as the tournament entry/prize accounting domain:

- the administrator sets an `entry_fee` and payout percentages for each actual field size from 2 through 6;
- defaults are winner-takes-all for 2–5 entrants and 70% / 30% for 6 entrants;
- registration debits the entrant through `point_ledger` and records the locked payment in `sitngo_payments`; insufficient balance does not block entry, so the official season balance may become negative;
- registration cancellation, administrator cancellation and minimum-player cancellation refund the recorded entry exactly once;
- the first registration permanently locks the event's point terms;
- registration is also the seating commitment: registered entrants are included at tournament start even if they never reopen the table, and their blinds/BBA continue to post while absent;
- tournament start fails closed if the registered field, locked fee, entry ledger rows or persisted payout configuration do not match exactly;
- finished tournaments settle through `sitngo_settlements` and `sitngo_prize` ledger rows, preserving the complete pool to 0.01 pt and verifying persisted awards on replay;
- manual admin reversal cannot independently reverse Sit&Go entry/refund/prize rows;
- while one Sit&Go is running, the player lobby can also expose the next scheduled/registration/starting event so an open registration window is not hidden;
- finished participants can see a ledger-backed point statement showing entry debit, refund, prize and net tournament point change;
- privacy-preserving Sit&Go runtime observability stores only aggregate counts for stale/duplicate/late actions, timeout boundary protection, automatic timeout actions and restart recovery; it stores no user, event, hand, card, chip, network or free-text identifiers; the admin Sit&Go view exposes the rolling seven-day aggregate counters and automatically surfaces conservative warning/critical banners for token-protocol mismatches, repeated stale actions and tournament restart recovery. Normal player timeout/check-fold activity is never an operator alert.
- CI includes a multi-session operational-acceptance regression in which independent member sessions act on one tournament and must converge on the same authoritative revision, turn, hand and stacks.
- `sitngo_games.state_json` is protected by up to 40 meaningful generations in `sitngo_state_backups`. Heartbeat-only clock/revision changes do not consume generations. If the authoritative JSON is malformed or structurally invalid, the runtime restores the newest validated same-event snapshot atomically before resuming.
- accumulated hand-history and tournament-chat reads are backed by composite `(event_id, created_at, id)`-ordered indexes (`hand_id` for hand history) so event-scoped reverse-chronological reads do not degrade into full-table scans as club history grows.

Paid end-to-end regression completes real 2-, 3-, 4-, 5- and 6-player tournaments. The 6-player path explicitly verifies each entry debit, escrow row, 70/30 winner/runner-up award, settlement record and prize-ledger row. PostgreSQL and SQLite Sit&Go CI both exercise the point integration.

## 11. Test ownership and release safety

`test_suites.py` owns active regression suites by concern. `production_release_gate.py` consumes the release selection rather than maintaining an independent list.

Important regression domains include:

- auth/security
- points integrity
- Ring gameplay
- browser contract and user journey
- runtime/release behavior
- Sit&Go
- PostgreSQL behavior

Historical one-off tests may remain for forensic value but are not automatically active release owners. Stage 6 root-core pruning and Stage 7B.2 legacy-artifact pruning are complete on `main`; current release coverage includes guards preventing those stale paths from returning. The Sit&Go canonical player source now expresses the 12-hand level model directly instead of relying on legacy timed-UI migration transforms.

The compatibility-runtime snapshot contract is now covered by `smoke_test_runtime_builder_snapshot.py` and the production release gate. A future change must not silently reintroduce runtime patch-chain replay. Active product regressions also validate canonical materialized/runtime behavior directly; they do not retain a source-level dependency on `v54_patch.py` or the old release reconstruction chain.

## 12. Current development philosophy

JJ Arena has accumulated features over many iterations. New work should use subtractive design where possible:

- prefer one canonical route/API/UI over parallel overlapping paths;
- retire superseded product surfaces deliberately;
- retain compatibility code only when it still protects stale clients, historical data, rollback or deterministic builds;
- do not delete compatibility machinery merely because it looks old without tracing its current dependency;
- add a new feature only when its product value justifies the added operational and UI complexity.

Sit&Go is an example of a feature judged important enough to add while other redundant surfaces are being reduced.

## 13. ChatGPT development workflow

Every new JJ Arena development chat should begin by reading, in this order:

1. `docs/PROJECT_STATE.md`
2. `ARCHITECTURE_STATUS.md`
3. `docs/DECISION_LOG.md`
4. the domain document relevant to the task (for example `docs/SITNGO_GAMEPLAY.md`)
5. `OPERATIONS.md` for production/deployment work
6. the latest handoff, if one exists

Then inspect current `main` and production when required. Do not assume the handoff's commit is still current.

When a chat becomes long or approaches its limit, do not try to preserve the whole transcript. Produce a handoff using `docs/CHAT_HANDOFF_TEMPLATE.md`. Promote durable decisions to `DECISION_LOG.md` and update this file if the canonical current state changed.

Once the durable state is captured in GitHub and the next chat has been validated against it, old ChatGPT development chats can be archived or deleted without making them part of the project's dependency chain.

## 14. Documents with distinct roles

- `README.md` — public/high-level project overview and basic setup.
- `docs/PROJECT_STATE.md` — canonical current project handoff state.
- `ARCHITECTURE_STATUS.md` — active / compatibility-only / retired architecture classification.
- `docs/DECISION_LOG.md` — durable reasons and policy decisions.
- `OPERATIONS.md` — deployment and production operations.
- `OPERATIONS_RECOVERY.md` / `ops/production_safety.md` — recovery and safety procedures.
- `docs/SITNGO_GAMEPLAY.md` — Sit&Go gameplay/technical contract.
- `docs/CHAT_HANDOFF_TEMPLATE.md` — compact transfer format between long ChatGPT sessions.

Do not turn `PROJECT_STATE.md` into a chronological changelog. Replace stale current-state statements instead. Historical reasoning belongs in the decision log; implementation history belongs in Git/GitHub.