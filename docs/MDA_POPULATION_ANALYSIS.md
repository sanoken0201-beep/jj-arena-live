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


## Phase 1 implementation (2026-10-15; draft PR #200)

The first foundation is available in this feature branch, **not deployed**:

- \`mda_foundation.py\`: standalone pure functions \`derive_decisions\`, \`derive_opportunities\`, \`summarize\`, \`coverage_report\`.
- \`mda_offline_audit.py\`: read-only PostgreSQL or SQLite connection with a recent-hand audit, at most 500 complete hands. It deliberately never imports app/FastAPI or reads hole-card/name columns.
- \`smoke_test_mda_foundation.py\`: synthetic action chronology and database fixture coverage, selected by \`test_suites.py\`'s production release suite.

Offline run, inside an environment that already has authorized database access:

\`\`\`bash
python smoke_test_mda_foundation.py
python mda_offline_audit.py --sqlite /path/to/local-jj.sqlite3 --limit 200
# Production shell: use the existing DATABASE_URL secret, never print/paste its value.
python mda_offline_audit.py --limit 200
\`\`\`

The CLI prints no raw identity, card or hand details. For all metrics, its API-safe summary suppresses exact counts if opportunities are fewer than 100 or distinct players fewer than 8. Running with \`--limit 200\` samples at most 200 **recent completed full-capture hands**, which is not necessarily representative and should not be taken as the true population rate. \`full_hands_missing_actions\` and \`recent_hands_rejected\` indicate further replay-validation needs. No query against real production data has been performed in this PR.

**Scope limitation:** the foundation treats effective stack as the *hand-start value*, not the true street-by-street effective stack. Flop bet_pct_pot is populated for unopposed first bets only; raises require a separate sizing definition. The 95% Wilson interval ignores player-level clustering. Do not infer a theoretically profitable exploit or GTO deviation from these raw rates. The feature pipeline and all its actor identifiers are private server-side material; do not expose its dataclasses or current participant hand-history access to generic member routes.


## Phase 1B: preflop empirical range vs. monotone-plus hypothesis (2026-10-15)

Goal: if a BTN **RFI** with \`K5o\` is observed, generate a **separate, explicitly tentative** candidate \`K5o+\`. Here \`K5o+\` expands to \`K5o, K6o, K7o, K8o, K9o, KTo, KJo, KQo\`. \`AKo\` and suited \`K5s\` are not included. One observed \`K5o\` open does **not** establish that \`K6o\` is opened at all, or that any of those hands is always opened.

New isolated files:
- \`mda_ranges.py\` pure utilities: hole-card canonicalization; all 169 starting-hand classes (1,326 actual combinations); per-class RFI evidence from known completed hand cards + real RFI opportunities; distinguish classes that were **seen and opened**, **seen and not opened**, and **unobserved**; plus expression expansion; optional explicitly labelled monotone kicker hypotheses with contradiction detection.
- \`mda_range_offline_audit.py\`: bounded (up to 500 completed full-capture hands) read-only audit of the **single current Ring table**. Sensitive player IDs and hole cards are read from trusted storage only into ephemeral in-memory private records. Public JSON outputs only anonymized class statistics with cohort and per-cell suppression. There are **no new API routes**, writes, browser changes, scheduled tasks or interaction with active tables.
- \`smoke_test_mda_ranges.py\` deterministic tests for parsing, plus notation, incomplete data, limp vs genuine RFI, sample suppression, in-memory privacy and coherent count weighting.

Privacy rules: at least 100 eligible RFI opportunities from at least 8 different players before any class grid is returned; individual class needs at least 12 opportunities from at least 4 different players. Below threshold, return \`unknown\` with no exact per-class count. Only eligible published seed classes can generate a published \`K5o+\` suggestion; no personal/rival hand range endpoint. The offline auditor must run only for an authorized administrator in a trusted setting. Do not log individual complete-hand hole cards, expose individual hand identities or make in-play overlays.

Statistical rules: a class open rate is \`open_count / total_eligible_opportunities_with_that_exact_class\` (not count of opens divided by all observed opens). \`Beta(1,1)\` smoothed frequencies and 95% Wilson binomial intervals apply only to **observed class cells**. For an unobserved \`K6o\`, the estimate remains \`unknown\`, not an automatic 100% or a fake 50%. The \`K5o+\` label is a *range-shape hypothesis* derived by assuming same-high-card/kicker monotonicity. Its seed can be supported by multiple observations, but it is never a proven GTO strategy. Explicit counterevidence from high-sample stronger kickers is flagged; naturally mixed fold frequencies are not simply classified as contradiction.

Important limitations:
- This first implementation covers RFI, not 3bet, call-vs-open, 4bet, limp-isolation, SB-completing, position/stack-adjusted mixed strategies, tournament ICM, or individual player profiling.
- \`A5s+\` is intentionally not automatically inferred, due to non-monotone wheel/blocker effects. Other suited/offsuit families can also violate a strength-ordered plus assumption; a future statistical model needs board-independent but context-specific range priors.
- Opening size, stack depth, six-max player count and changing rake/rule settings are potential confounders. Do not pool mismatched formats and then label the result as a solver-matched range.
- There is no preflop range heatmap in the live app yet. A future study-mode range grid should use distinct styling for **actual observations**, **heuristic continuation** and **unknown cells**, with no automatic coloring of extrapolated cells as observed.

Local/tests (trusted environment with already-authorized DB access):

\`\`\`bash
python smoke_test_mda_ranges.py
python mda_range_offline_audit.py --sqlite /path/to/local-jj.sqlite3 --position BTN --limit 500
# With an existing authenticated DATABASE_URL available only to the trusted shell:
python mda_range_offline_audit.py --position BTN --limit 500
\`\`\`

Never paste production DB URLs, PINs or raw card records into chat/GitHub. This design is not production-activated until CI, data quality, privacy and performance reviews pass.


## Phase 1C: mandatory table occupancy and revisable estimates (2026-10-15)

Every preflop RFI evidence item and aggregate **requires** a validated \`table_size\` equal to the number of players actually dealt in when the hand began. The actual source is \`jj_hand_history.player_count\` established at hand start; do NOT use the table's maximum seat capacity, live seat occupancy, or a subsequent hand's occupancy. Reject incomplete/mismatched player snapshots. **Never pool 2, 3, 4, 5 and 6 dealt-in hands into one inferred range**. A 6-handed BTN K5o open offers no evidence for a 3-handed BTN K5o strategy.

The position mapping follows JJ's existing recorded \`hand_analytics._position_map\`:

| Dealt-in players | Valid positions |
| --- | --- |
| 2 | BTN/SB, BB |
| 3 | BTN, SB, BB |
| 4 | BTN, SB, BB, CO |
| 5 | BTN, SB, BB, UTG, CO |
| 6 | BTN, SB, BB, UTG, HJ, CO |

For RFI only, the BB is never a qualifying opener. On a heads-up table, the button posts the small blind and acts first preflop; \`BTN/SB\` is a distinct key. Do not map HU \`BTN/SB\` to a six-handed \`BTN\`.

Updated offline auditing (\`mda_range_offline_audit.py\`) now **requires** both \`--table-size\` and \`--position\`, applies the player-count SQL filter *before* the hand limit, and reads players/actions in batches of up to 200 hand IDs (not two remote round trips for each hand). Defaults to latest 5,000 completed full-capture Ring hands for that table size, with an explicit upper bound of 50,000. This is a bounded, offline-only **rolling window**; if all-time results are required, separate batch cursoring and a cumulative projector are needed.

### Updates, reclassification and withdrawal

Running the read-only audit again recomputes the **entire selected current source window**, rather than retaining any prior inferred class as permanently true. Accordingly:
- Observed hand decisions remain evidence only while the underlying completed hand record is valid and present.
- Published open frequencies can rise or fall with new evidence, corrections and window movement. A previously observed cell can become \`unknown\` if it falls below privacy/quality thresholds.
- Monotone-plus hypotheses, including a previously \`seed_replicated\` K5o+, can change, acquire counterevidence, or be withdrawn entirely; \`seed_replicated\` means the seed has repeated observations, **not that the whole plus range is confirmed**.
- A snapshot revision is a recomputation/reconciliation of evidence, not an overwrite of individual historical actions.
- \`mda_range_revisions.compare_range_reports(old, new)\` deterministically reports changed observed frequencies, newly observable and withdrawn cells, added/changed/withdrawn hypotheses, and loss of population sufficiency. It deliberately **refuses** comparisons across distinct table sizes, positions, table identifiers, format versions, sampling methods and \`--limit\` values.
- The tool does not create background workers or write snapshot tables in the production database. The source history remains authoritative. The offline operator supplies the previous sanitized JSON snapshot to opt in to a revision comparison.

Example workflow (trusted admin machine; do not publish old or new files outside private controls):

\`\`\`bash
python mda_range_offline_audit.py --table-size 6 --position BTN --limit 10000 > private-prev.json
# Later after new completed hands are present:
python mda_range_offline_audit.py --table-size 6 --position BTN --limit 10000 --compare-json private-prev.json > private-current.json
python mda_range_offline_audit.py --table-size 2 --position BTN/SB --limit 10000
python smoke_test_mda_range_revisions.py
\`\`\`

This means estimates **can be updated and prior conclusions retracted on every audit invocation**, but automatic background refresh, durable revision storage and visualization remain a later, explicitly reviewed stage. Never run these large privacy-sensitive queries in an active table websocket/request handler or expose fine-grained snapshot differences to members or opponents.

All old examples omitting \`--table-size\` are superseded by these Phase 1C examples.


## Phase 1D: analyze every recorded player (2026-10-15)

**Clarification: the population is not administrators only.** Admin-only described the credentials required to execute a trusted offline job, **not a filter on whose hands are studied**. The MDA source is every participant recorded in eligible hands, whether the account is an administrator or an ordinary member. The queries do not join or filter on users.role, user identity, account privileges, or a requesting admin's hand involvement.

The new file mda_all_players_offline_audit.py performs a full-history (by default) cursor-paginated read-only scan across completed, fully recorded hands of public Ring table jj-table-a. It includes ALL dealt-in participants from 2, 3, 4, 5 and 6 handed games, without pooling those cohorts, and all recorded decisions, including decisions made by players without an available 2-card record. Metrics derive from actual action opportunities and remain grouped by dealt-in table size and position. Where cards are valid, the same data also contributes to the 169-class empirical RFI range and tentative, revisable plus hypotheses. The BB is counted among player/decision coverage and in other applicable metrics even though BB RFI is not applicable. No user account role filter exists.

- Default invocation: python mda_all_players_offline_audit.py --sqlite /path/to/local-jj.sqlite3
- Authorized production shell: python mda_all_players_offline_audit.py (requires already configured DATABASE_URL).
- Test-only bounded subset: python mda_all_players_offline_audit.py --max-hands 500. This is clearly marked as a **partial** scan, not the full population.
- Regression: python smoke_test_mda_all_players.py.

The processing does not hold the entire raw hand history in memory. It fetches 200 complete hands at a time, joins their players/actions in batches, and retains anonymizable class/metric counts and internal unique-player sets for thresholding. Neither raw cards nor individual hand IDs/user IDs are serialized to output. All statistical strata remain subject to group and 169-class sample suppression, and no person-specific profile is returned.

**Important distinction:** at this phase, all hands **are data inputs**, but only authorized administrators can execute the offline data processing tool. There is no live API, member dashboard, opponent HUD or public full card-history access. A future member-accessible feature should show only sufficiently aggregated, delayed population frequencies after a privacy/security review. Individual players may continue viewing their own already-authorized hand analyses.

This implementation covers the Ring historical source; Sit&Go records are stored separately and still need a separate ingestion/replay adapter before they can be claimed as part of *all online poker formats*. Likewise, missing/partial hands cannot safely be treated as complete evidence; the scan reports rejected records. No verified live production counts are implied by adding this code.


## Phase 1E: Sit&Go completed-hand RFI adapter (2026-10-15)

Ring and Sit&Go currently store history differently. The Sit&Go code persists finished-hand snapshots in sitngo_hands.state_json (hand id, event id, created timestamp, full completed state), not in Ring's jj_hand_actions table. Existing Sit&Go hand["log"] contains **human-readable** messages such as "Name folds", "Name calls N bb", and "Name raises to N bb"; there is no persisted typed action sequence or pre-action pot/facing amount. Pretending those logs have the same reliability as Ring's structured action history would corrupt MDA.

New trusted **offline, read-only** adapter: mda_sitngo_offline_audit.py.

- Reads all historical completed Sit&Go snapshots by keyset cursor (created_at, hand_id) with a fixed batch bound (100) and a single read snapshot/transaction. The optional --max-hands N labels a partial sample.
- Uses the completed hand's starting_stacks to determine **who was actually dealt in** (2–6), reconstructs preflop seats relative to the recorded button, and matches one-to-one unique participant names from the snapshot to the saved log. Every registered player's hand can be analyzed when data is complete, regardless of their account role.
- Extracts **only defensible unopened RFI opportunities** (fold vs open) from unambiguous preflop actions before the next street. First calls, including non-raising all-ins, close the unopened opportunity; ambiguous logs, duplicate names, incomplete or mismatched states are rejected for this stage. Missing hole cards never become inferred observations. Participant coverage includes hands even when no one has RFI action available.
- Aggregates privacy-suppressed 169-class RFI by *Sit&Go* format, table size and position, keeping these separate from Ring. Reuses the exactly same anonymous statistics and plus-hypothesis labeling as the Ring audit. Includes counterevidence and permits recomputation on new data, not frozen conclusions.
- Reports number of scanned, accepted and rejected snapshots and rejection categories. Never includes names, exact private cards, user IDs, hand IDs, decks or raw snapshots in results.
- No in-play HUD, new API, game/database mutation, tournament points/ranking impact or automatic background jobs.
- Unit and end-to-end regression: smoke_test_mda_sitngo_ingest.py tests log parsing, duplicate names, missing cards, all-player aggregation/privacy suppression, cross-format separation, recomputation, and a finished hand actually played through the canonical tournament engine.

Run only with already-authorized read access, on a trusted admin machine:

    python smoke_test_mda_sitngo_ingest.py
    python mda_sitngo_offline_audit.py --sqlite /path/to/jj.sqlite3
    python mda_sitngo_offline_audit.py

Caveats: Do not claim Sit&Go full street-by-street MDA. **3Bet, 4Bet, pot-relative sizing, flop cbet, ICM**, and postflop decision sequences need a future **structured and append-only Sit&Go action capture** (designed without slowing the action path). A text log is insufficiently precise for such claims. Privacy thresholds and statistical cluster-dependence warnings apply separately to tournament hands. The production Render workspace and database need confirmed scope before any actual-data read, so this stage creates only the parser and offline CLI, not verified live estimates.


## Phase 1F: production coverage gate and 13x13 presentation contract

The connected Render dashboard confirms the primary PostgreSQL 18 database is available. Its external IP allowlist is empty, so the hosted connector's direct SQL query is BLOCKED. Keep external connection blocked: no permissive IP allowlist or credentials exported to a third party.

### Cheap trusted internal coverage gate

After review and deployment of the source to the already-linked service, open the existing Render service Shell (internal private database network) and run:

    python mda_coverage_gate.py

On a read-only SQLite copy:

    python mda_coverage_gate.py --sqlite /path/to/local-copy.db
    python smoke_test_mda_range_grid_coverage.py

The command reads SQL aggregates only; it never returns names, hole-card values, IDs or individual hand rows. Reports stored/completed/full-capture Ring hand counts by actual dealt-in 2–6 players, distinct members, card-missing counts, hands with recorded actions, and overall Sit&Go snapshots/events; also checks presence of the required source tables. The PostgreSQL connection is read-only with a 5-second per-statement timeout. Results are coarse coverage checks, NOT actual 169-class RFI samples or solver-verified ranges.

Do not run heavyweight historical MDA on the small primary during gameplay without checking timeouts, query plans, resource headroom, and sample size. Prefer off-peak execution or an isolated replica for large data.

### Privacy-preserving 13x13 grid

mda_range_grid.py provides a pure range_matrix(sanitized_report, table_size=6, position="BTN") function from already suppressed offline data, accepting Ring and Sit&Go population audit JSON and range-only rfi-range-v2 JSON. No database connection or card access is needed.

13 ranks A..2 run down both axes. Pairs are diagonal, suited classes above diagonal, offsuit below. Each of the 169 cells has exactly one primary status:

- observed: actual sample-qualified RFI action percentage and number of opportunities. NOT theoretical opening range certainty.
- hypothesis: an unobserved stronger-kicker candidate from an independently publishable observed seed and a validated plus assumption without counterevidence. No inferred action percentage is ever filled.
- unknown: insufficient evidence. Never interpret as 0% or 100%.
- Entirely suppressed cohorts show 169 unknown cells; even if accidentally present, per-class data is ignored.
- A withdrawn/contradicted hypothesis reverts to unknown rather than persisting in a cache.
- Games (Ring/Sit&Go), actual table sizes (2..6), and positions remain strictly independent. HU BTN/SB is not the six-handed BTN. BB RFI is not applicable.

Generate output from already sanitized reports:

    python mda_range_grid.py --input sanitized-ring.json --table-size 6 --position BTN
    python mda_range_grid.py --input sanitized-sitngo.json --table-size 2 --position BTN/SB
    python mda_range_grid.py --input sanitized-ring.json --table-size 6 --position BTN --no-hypotheses

The output is structured JSON ready for an eventual lightweight, cached visual table. No live app route or UI is added. Public/member delivery requires a separate privacy and differencing review: delayed snapshots, suppressed small cohorts, and rate limits should prevent reverse engineering hidden cards or recent actions.


## Phase 1G: admin-only cached MDA dashboard and offline publishing

The analyzed population continues to include ALL recorded Ring and Sit&Go participants regardless of account role. The new permission distinction is that aggregate review is limited to administrators and never reveals a per-opponent hand.

Architecture:

- mda_snapshot_cache.py: offline full-history Ring and Sit&Go scan on a trusted host; reject partial sample publications; prepare only anonymous per-game, per-dealt-in-table-size, per-position 13x13 grid data; optional explicit publication of at most 40 rows into the durable PostgreSQL table jj_mda_population_cache. Publish all rows atomically at the end of a completed scan. No original user IDs, exact hole cards, player names or hand identifiers are retained in cache.
- mda_admin_api.py: private admin route at /api/admin/mda/grid?game=Ring&table_size=6&position=BTN. Protected by the existing server.admin_user dependency. One indexed cache SELECT, no full-history scan, no writes, no user-specific query and no live HUD.
- materialized_v1244/static/index.html and mda-view.js / mda-view.css: a new administrator-only responsive population MDA tab. It loads only on activation; format, actual table size and position controls; horizontal scrolling on narrow phones. Observed percentage, plus candidate and suppressed unknown have distinct styling and labels. No table-state listeners, no timers, no WebSocket/polling additions.
- app_materialized.py mounts the route without creating or reading any large database table on app startup.
- smoke_test_mda_admin_cache.py verifies sample and role separation, non-admin access denial before database hit, revisions/withdrawals, and safe row-only GET.

### Operator sequence

1. Review/merge staged draft PRs #200 through #206; the new CLI is only present in the deployed branch.
2. First run the low-cost internal DB coverage gate and inspect actual count/record quality. Keep the production database's external IP allowlist closed.

       python mda_coverage_gate.py

3. Prefer executing full-history scans off peak in a separate background or Render Cron worker, ideally using a replica, not the web worker handling games. The primary PostgreSQL is small; examine resource headroom. Publishing requires explicit acknowledgement:

       python mda_snapshot_cache.py --permit-primary-scan
       python mda_snapshot_cache.py --permit-primary-scan --publish

   First is a non-writing dry run. Second atomically writes only sanitized population grid cache rows. Local SQLite test source supports dry run without write using --sqlite.

4. Open the MDA tab while signed in as an administrator. If no cache has been published, the tab says that no snapshot is ready. A frontend request never triggers an expensive scan.

Automatic refresh is **prepared but NOT activated**. An off-peak separately configured Render Cron can run the publishing command, but creating a scheduled service may incur hosting costs and full-table DB load. This PR does not create the cron resource or automatically deploy it. Render services do not share persistent filesystems; using a durable DB cache prevents ephemeral Cron/Web differences. Member-facing aggregated MDA access is not enabled until additional disclosure/differencing review.

This is not a completed live production data audit. All CI assertions run on disposable fixtures. The public Ring source is still jj-table-a and the Sit&Go source is sitngo_hands.
