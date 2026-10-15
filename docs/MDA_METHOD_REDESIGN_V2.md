# MDA v2 — online-table empirical population statistics

## Methodological reset (2026-10-16)

The previous MDA design used a small number of observed starting-hand decisions as seeds and interpolated plus-ranges such as K5o+ for **unobserved** kickers. That does NOT follow from the data and must not be called an inferred range. All prior draft PRs #200–#208 are unmerged, and the legacy 169-class grid is RETIRED as a primary MDA report. A poker hand class not observed in play is not evidence of a zero opening strategy, and even a zero observed rate with actual opportunities still has a nonzero statistical upper bound.

**New objective:** study population tendencies in the same spirit as conventional mass data analysis, using only actual completed **JJ Arena online Ring tables** and their server-recorded structured hand histories. A simple statistic is actions chosen / eligible opportunities in a precisely defined situation, NOT how many different hand classes appear in the sample.

Examples (illustrative, not JJ live data):
- 3-bet: 12 raises / 100 genuine first-3-bet opportunities => observed 12%. The other hands in which no raise was faced do NOT enter this denominator.
- K5o never seen: unknown availability and unknown inclusion. No plus-extension to K6o..KQo is permitted.
- 0 bets / 120 valid betting opportunities: descriptive point estimate 0%, but the true frequency is not proven to be 0%. Never call it an excluded strategy/hand. Wilson uncertainty must be displayed alongside the sample.

## Authoritative source

The hand pipeline is already installed in hand_analytics.py; it records complete online Ring hands to:
- jj_hand_history: IDs, official online table IDs, timestamps, participation, blinds and board.
- jj_hand_players: dealt-in members and seats/positions; the server also stores private hole cards, but **v2 never SELECTs these columns**.
- jj_hand_actions: actions, recorded pot before bet, facing amount, action sequence, street and timeout status.

V2 queries only fully captured completed hands with source table_id in (jj-table-a, jj-table-b). It rejects wrong/partial/unfinished histories and noncanonical player/position/action records. Both members and administrators are included; no user role predicate is applied. Hands from unrelated/custom tables are excluded. The format is Ring only; Sit&Go is a different tournament population and is NOT pooled into v2, even though the application hosts online Sit&Go games.

## What is aggregated

From mda_foundation.py, the first supported decision types are:
- RFI: chance to voluntarily open before another player enters, recorded by position.
- 3-bet: facing a previous open with a real response chance.
- Fold to 3-bet: opener directly facing the first 3-bet.
- Flop c-bet: preflop aggressor acting without a preceding flop bet.
- Fold to flop c-bet: direct chance to respond to a flop c-bet.

Every metric retains its own eligible denominator, outcome counts and Wilson-style descriptive interval; action timeouts are excluded from *voluntary strategic decisions*. Stratifications are independent: actual 2–6 player table size, position, pot type, effective starting stack bucket and (postflop) board texture. Do not blindly multiply all dimensions into sparsely populated micro-cohorts. The current extractor does not yet establish a complete taxonomy of multiway/pot-size subtleties, so the metric definitions must continue to be audited against realistic sequences before broad claims.

Suppression: 100 metric opportunities AND 8 distinct contributing players per public reportable cell, otherwise only "insufficient_sample" appears. Suppression does not mean zero. Wilson bounds currently do not adjust for repeated decisions by the same individuals. The sample can be unrepresentative of other games/stakes/time periods. No solver or GTO benchmark is assumed; solver comparison would require matched rake, effective stacks, format and exact decision node.

## Code and migration

- mda_online_population_v2.py: read-only, cursor-paginated scanner. No private cards, player names or IDs in serialized output; no live hand or WebSocket integration. CLI supports --sqlite and a clearly partial --max-hands diagnostic.
- mda_online_review_v2.py: prepares a privacy-suppressed **read-only aggregate review** from a verified complete online-source scan. This does not publish a dashboard or modify PostgreSQL.
- smoke_test_mda_online_population_v2.py: simultaneous Table A/B records, no decisions mislabeled excluded, a 0/N case with nonzero Wilson upper bound, 2/3/6 player independence, absence of hole-card SQL reads and partial sample rejection.
- mda_admin_api.py: the OLD admin 169-class grid endpoint remains authenticated but always returns not_ready; it never queries any legacy inferred range cache, regardless of past flags.
- mda_snapshot_cache.py: the old plus-inference snapshot CLI terminates before querying or writing any DB. The old 169 range and test utilities remain only for historical compatibility/tests; they must not be republished or reused as v2 empirical conclusions.

### Production operations

No merge, Render environment modification, scheduled job, direct production query, cache publication or frontend-data release occurs with this methodology reset. Before future deployment and live analysis: review the source and decision-denominator definitions, obtain actual Table A/B anonymous coverage and analyze a small sample offline on the internal network, then choose cost/refresh windows. A redesigned dashboard should present opportunity-conditioned actions, sample counts, reliability and contexts, NOT filled-in 169 opening grids. Privacy and delayed/suppressed results remain required.

If a future phase introduces class-level frequencies, it must distinguish P(open | **dealt** class, eligible opportunity) from P(class | **observed open**) and from the underlying unknown strategy. Zero observed opens and unavailable dealt cards are not equivalent. No class may be declared excluded based solely on nonobservation.

References for methodology: GTO Wizard Aggregate Reports (aggregation conditioned on contexts); Poker MDA mass data analysis descriptions (population frequencies by spot); PokerTracker opportunity-based HUD counting.
