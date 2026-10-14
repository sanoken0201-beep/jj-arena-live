# JJ Population MDA — architecture and implementation plan

Status: design / no production activation
Created: 2026-10-14
Scope: offline, server-side analysis of completed Ring hands; separate future Sit&Go pipeline.

## Goal

Build an MDA-like **population decision explorer**, NOT a live-table opponent HUD. A user chooses a spot (positions, pot type, effective stack, actions/sizing, board texture, streets), sees the exact number of eligible decisions and fold/call/raise frequencies, and can browse subsequent nodes. GTO comparison may be added from independently verified, configuration-matched solutions; raw population frequencies are NOT GTO and do not by themselves establish positive EV.

## Repository facts verified from main

- App is Python/FastAPI, PostgreSQL in production, SQLite in local tests; production uses a single low-resource Render worker and existing `jj-arena-db`.
- Production core `materialized_v1244/` is immutable. Root-level extensions install from `app_materialized.py`; browser assets compile via `served_assets.py` and `browser_asset_pipeline.py`. Do not edit the core or create a new DB.
- Ring analysis already persists:
  - `jj_hand_history`: hand id, game/table, blinds, completed status, showdown, board, player count, `partial_capture`.
  - `jj_hand_players`: participant ID/position/effective stack, opportunity flags (3bet, cbet, etc.), and **private hole cards**.
  - `jj_hand_actions`: chronological actions, user, street, chips/BB, pot before, amount facing, aggression, raise count, timeouts.
  - `jj_hand_snapshots`: selected sanitized game states.
  - `jj_hand_reviews`: participant's private hand bookmarks/notes.
- These data are captured by `hand_analytics.py`; `hand_analytics_hardening.py` refines stat definitions and excludes best-effort-marked partial records from normal player aggregates.
- Current `/api/analysis/*` routes are user-scoped personal Poker Lab reports, not a population endpoint.
- Sit&Go is separate. `sitngo_runtime.py` stores completed `sitngo_hands.state_json`, but cannot be assumed to have `jj_hand_actions` coverage. DO NOT silently mix Ring and Sit&Go distributions.
- Historical `online_hands` / `online_hand_results` are settlement summaries and must not be treated as complete historical action data.

## Product boundaries

1. Admin-only and **post-session/study mode only** for first release. Never publish live, near-live, or individual-villain reads while a hand is ongoing. Review permissions before a wider member release.
2. Population aggregates only: no user_id, player name, session token, private hole-card combo, identifiable hand list, or showdown reconstructed from unrevealed private cards in public responses.
3. Separate restricted forensic participant hand-review behavior from population analysis. Existing participant-only hand visibility rules must not be bypassed.
4. Suppress small cells: provisional minimum 100 eligible opportunities, at least 8 distinct players, and report the dominant player's share where internally available. Stricter thresholds/consent might be needed for a small club cohort.
5. No on-demand full scan of raw `jj_hand_actions` during live gameplay; no background polling. Analytics failure must never block or alter action, settlement, ranking, point ledger, WebSocket, timeout or card privacy.
6. Respect logical account deletion: avoid public reidentification and define explicit anonymized historical aggregation retention policy before enabling aggregate sharing.

## Core analytical definitions

**Unit of observation** = ONE *eligible decision opportunity*, not an entire hand. `num = decisions taking chosen action`, `den = decisions eligible to take that action`; show both. For example fold-to-flop-cbet denominator only counts actors who really faced that cbet, not all players who saw the flop.

- VPIP/PFR per dealt hand; 3bet and fold-to-3bet per genuine opportunity; cbet per first unfaced preflop aggressor flop decision; fold-to-cbet for direct responders only.
- For a node facing a bet, options = fold/call/raise; for no bet = check/bet; classify all-in calls vs all-in raises by whether the action increases the wager. Separate forced timeout-fold from intentional fold in model diagnostics.
- Pot type = limped / SRP / 3bet / 4bet+ determined by preflop *chronology* and genuine aggressions, not number of players.
- Position = seat relation BTN/SB/BB/HJ/CO/etc; for postflop heads-up derive IP/OOP relative to the remaining players, never only by initial absolute position.
- Bet sizing: report precise chips and BB, **bet fractions of pre-bet pot only for first bets**, plus separate definitions of raises (to-size and effective increment). An all-in short raise must not be counted as full re-open.
- Derived filters: game=Ring; date range; heads-up/multiway; exact line; PFA, defender and positions; effective stack at action; board high-card/pairing/connectivity/suits; pot type and previous bet/raise sizes.
- Never use a showdown-only sample to infer underlying starting hand distribution. Complete server-held hole cards may allow **restricted validation** of folded-hand combinatorics, but any public output derived from such cards needs an explicit privacy review.
- GTO comparison is a separate optional module requiring matching stacks, positions, raise sizes, number of players, rake, and other relevant rules.

## Data pipeline

Phase 0 — read-only audit:
- Count completed full-capture Ring hands, player rows, action rows, date coverage and `partial_capture` rate.
- Reconcile raw actions against `hand.log`/snapshots for sample hands, including fold/raise/all-in, timeout, reconnect and duplicates.
- Audit whether each existing flag's opportunity denominator agrees with chronological replays. Record the engine/analytics version boundary.

Phase 1 — offline reproducible decision extraction:
- Add a standalone `mda_features.py` with pure logic `derive_decisions(hand, players, actions, snapshots)` and unit fixtures; no changes to poker engine.
- Write an incremental, versioned, idempotent projector of **only completed full-capture Ring hands** into a new `jj_mda_decisions` table or an equivalent compact materialization, without raw hole-card columns.
- Columns (draft): `hand_id`, `seq`, `feature_version`, `street`, `actor_position`, `actor_position_ip`, `pot_type`, `player_count_at_action`, `effective_stack_bb_at_action`, `board_texture`, `prior_line_key`, `facing_amount_bb`, `pot_before_bb`, `bet_size_pct_pot` (nullable), `action_family`, `timed_out`. Retain user linkage only in restricted storage for bias diagnostics and aggregate distinct-player thresholds, never the public response.
- Unique key `(hand_id,seq,feature_version)`; process in bounded batches by a stable watermark, only off the real-time critical path.
- Preserve schema backwards compatibility and prioritize a compact row/index budget; current DB is small. Do not duplicate whole state JSON or write per-action expensive synchronous aggregations.

Phase 2 — aggregate read API and UI:
- New root extension `mda_api.py`, routes `GET /api/admin/mda/coverage`, `GET /api/admin/mda/summary`, `GET /api/admin/mda/node`. Require `admin_user`; whitelist filters, bounded limits, server-driven queries, rate limits/timeouts, parameterized SQL.
- UI should be a separate study panel from the active table: desktop filters and a narrow mobile layout, sample-size labels, confidence/credible intervals, action bar chart, breadcrumb for drilldown and clear “insufficient sample” states.
- Cache versioned materialized aggregates and use seek pagination; requests must never evaluate arbitrary SQL from a client.
- Do not show private raw hand detail links in population response. Existing `/api/analysis/hands/{hand_id}` participant checks remain authoritative.

Phase 3 — evaluate and expand:
- Coverage-adjusted preflop and flop first; add turn, river and line-specific bet-size comparisons only when opportunity counts support them.
- Validate against hand replay spot fixtures and confidence intervals (Wilson 95% initially). Distinguish opportunity count, distinct player count and effective sample dominated by repeat players. Use temporal holdout and sensitivity to highly active players.
- Optional: participant-consented advanced range composition, delayed study-mode cohort comparisons, and separately verified solver baseline.
- Sit&Go obtains an independent projector and tournament phase/ICM filters if raw chronological replay fidelity is established; never merge tournament and Ring outcome statistics.

## MVP acceptance

- Historical partial/in-progress hands contribute **zero** to core rate numerators/denominators.
- Each denominator is backed by a verified eligible action, not a hand count guess; multiway overcalls/3bet/squeeze/cbet/donk/all-in fixtures covered.
- Repeated projection is idempotent, schema remains backward compatible, and no connection leak / heavy full scan occurs on a table WebSocket or action path.
- Zero raw hole cards, names, hand IDs or user IDs appear in aggregate API JSON, HTML or logs.
- Suppression for small counts/unique players is independently regression-tested.
- Mainline scoring/points/ranking/tournament/rake and participant hand-review privacy are byte-for-byte behaviorally unaffected.
- SQLite and PostgreSQL integration, security, production startup, desktop/mobile browser, and baseline runtime performance gates pass before any main merge.
- Release remains branch → PR → CI → main → existing Render service; production SQL is read-only until an explicit migration/release plan is approved.

## Decisions to settle before public release

- Should members ever see only their own comparative cohort metrics, or full anonymous population?
- Is publication of **any** non-showdown hidden-card-derived distributions acceptable? Default = no.
- Are timeout actions separate from regular human actions in the official sample? Default = yes.
- Are samples pooled across all season/room/rule changes? Default = segregate and explicitly filter.
- What are actual completed/valid hand counts and DB growth? Requires read-only production coverage check with confirmed Render workspace.
