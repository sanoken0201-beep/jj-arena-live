-- JJ Arena production rake integrity audit (READ ONLY)
--
-- Purpose:
--   1) verify stored ring-game rake/result invariants;
--   2) distinguish historical policy windows so the former 10%/5bb policy is
--      not misclassified as a current-policy defect;
--   3) surface legacy rows affected by the historical No Flop No Drop metadata
--      gap without modifying any production data.
--
-- Production milestones (UTC):
--   2026-09-14 15:59:55.992406Z  uncalled-contribution settlement fix live
--   2026-09-14 16:17:08.642886Z  5% / 3bb policy live
--   2026-09-14 17:43:56.661173Z  No Flop No Drop metadata fix live
--
-- Every statement below is SELECT-only. The explicit READ ONLY transaction is
-- useful when running with psql; Render's database query tool also enforces a
-- read-only transaction independently.

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '20s';

SELECT
  current_timestamp AS snapshot_time,
  COUNT(*) AS hand_count,
  MIN(played_at::timestamptz) AS first_hand,
  MAX(played_at::timestamptz) AS latest_hand
FROM online_hands;

-- Current persisted table policy. Rows returned by the second query are defects.
SELECT
  id,
  name,
  (state_json::jsonb->>'big_blind')::numeric AS big_blind,
  (state_json::jsonb->>'rake_percent')::numeric AS rake_percent,
  (state_json::jsonb->>'rake_cap')::numeric AS rake_cap
FROM tables
WHERE state_json::jsonb ? 'rake_percent'
ORDER BY id;

SELECT
  id,
  name,
  state_json::jsonb->>'big_blind' AS big_blind,
  state_json::jsonb->>'rake_percent' AS rake_percent,
  state_json::jsonb->>'rake_cap' AS rake_cap
FROM tables
WHERE state_json::jsonb ? 'rake_percent'
  AND (
    COALESCE(NULLIF(state_json::jsonb->>'rake_percent','')::numeric, -1) <> 0.05
    OR COALESCE(NULLIF(state_json::jsonb->>'rake_cap','')::numeric, -1)
       <> COALESCE(NULLIF(state_json::jsonb->>'big_blind','')::numeric, 0) * 3
  )
ORDER BY id;

-- Policy-window inventory. This is informational, not an anomaly report.
WITH policy AS (
  SELECT
    '2026-09-14T15:59:55.992406Z'::timestamptz AS uncalled_fix_at,
    '2026-09-14T16:17:08.642886Z'::timestamptz AS rake_5_3_at,
    '2026-09-14T17:43:56.661173Z'::timestamptz AS noflop_fix_at
)
SELECT
  CASE
    WHEN h.played_at::timestamptz < p.uncalled_fix_at
      THEN 'legacy_before_uncalled_fix'
    WHEN h.played_at::timestamptz < p.rake_5_3_at
      THEN '10pct_5bb_after_uncalled_fix'
    WHEN h.played_at::timestamptz < p.noflop_fix_at
      THEN '5pct_3bb_before_noflop_metadata_fix'
    ELSE 'current_5pct_3bb'
  END AS policy_window,
  COUNT(*) AS hands
FROM online_hands h
CROSS JOIN policy p
GROUP BY 1
ORDER BY MIN(h.played_at::timestamptz);

-- Referential and denormalized-field integrity. Every query should be empty.
SELECT r.id, r.hand_id, r.user_id, 'orphan_result' AS anomaly
FROM online_hand_results r
LEFT JOIN online_hands h ON h.hand_id=r.hand_id
WHERE h.hand_id IS NULL
ORDER BY r.hand_id, r.id;

SELECT
  r.id,
  r.hand_id,
  r.user_id,
  'hand_result_metadata_mismatch' AS anomaly,
  h.table_id AS hand_table_id,
  r.table_id AS result_table_id,
  h.month AS hand_month,
  r.month AS result_month
FROM online_hand_results r
JOIN online_hands h ON h.hand_id=r.hand_id
WHERE r.table_id IS DISTINCT FROM h.table_id
   OR r.month IS DISTINCT FROM h.month
ORDER BY r.hand_id, r.id;

SELECT
  hand_id,
  user_id,
  COUNT(*) AS duplicate_rows,
  'duplicate_user_result' AS anomaly
FROM online_hand_results
GROUP BY hand_id, user_id
HAVING COUNT(*) > 1
ORDER BY hand_id, user_id;

-- Ranking points are derived: 1bb = 3 points.
SELECT
  id,
  hand_id,
  user_id,
  result_bb,
  points,
  ROUND(result_bb * 3, 2) AS expected_points,
  'points_mismatch' AS anomaly
FROM online_hand_results
WHERE ABS(points - ROUND(result_bb * 3, 2)) > 0.001
ORDER BY hand_id, id;

-- Hand-level conservation and completeness.
-- For a correctly settled hand: SUM(player net bb) + rake bb = 0.
WITH rollup AS (
  SELECT
    h.hand_id,
    h.table_id,
    h.played_at::timestamptz AS played_at,
    h.gross_pot_bb,
    h.rake_bb,
    h.voided,
    hh.reached_street,
    hh.player_count,
    COUNT(r.id) AS result_count,
    COALESCE(SUM(r.result_bb),0) AS sum_result_bb
  FROM online_hands h
  LEFT JOIN online_hand_results r ON r.hand_id=h.hand_id
  LEFT JOIN jj_hand_history hh ON hh.hand_id=h.hand_id
  GROUP BY
    h.hand_id,h.table_id,h.played_at,h.gross_pot_bb,h.rake_bb,h.voided,
    hh.reached_street,hh.player_count
)
SELECT
  *,
  ROUND(sum_result_bb + rake_bb, 4) AS conservation_error_bb,
  'hand_conservation_or_completeness' AS anomaly
FROM rollup
WHERE gross_pot_bb < 0
   OR rake_bb < 0
   OR ABS(sum_result_bb + rake_bb) > 0.011
   OR (player_count IS NOT NULL AND result_count <> player_count)
ORDER BY played_at, hand_id;

-- Time-aware rake formula verification.
-- Ring-game BB is 100 chips in the persisted online-hand model:
--   old: min(floor(gross_chips*10%), 5bb)
--   new: min(floor(gross_chips*5%),  3bb)
-- No Flop No Drop: reached_street='preflop' => rake 0.
-- Rows without jj_hand_history are reported separately because No Flop status
-- cannot be inferred safely from online_hands alone.
WITH policy AS (
  SELECT '2026-09-14T16:17:08.642886Z'::timestamptz AS rake_5_3_at
),
evaluable AS (
  SELECT
    h.hand_id,
    h.table_id,
    h.played_at::timestamptz AS played_at,
    h.gross_pot_bb,
    h.rake_bb,
    hh.reached_street,
    CASE
      WHEN hh.reached_street='preflop' THEN 0::numeric
      WHEN h.played_at::timestamptz >= p.rake_5_3_at
        THEN LEAST(FLOOR(h.gross_pot_bb * 5) / 100, 3::numeric)
      ELSE LEAST(FLOOR(h.gross_pot_bb * 10) / 100, 5::numeric)
    END AS expected_rake_bb
  FROM online_hands h
  JOIN jj_hand_history hh ON hh.hand_id=h.hand_id
  CROSS JOIN policy p
)
SELECT
  *,
  ROUND(rake_bb - expected_rake_bb, 4) AS rake_error_bb,
  'rake_formula_violation' AS anomaly
FROM evaluable
WHERE ABS(rake_bb - expected_rake_bb) > 0.001
ORDER BY played_at, hand_id;

WITH policy AS (
  SELECT '2026-09-14T17:43:56.661173Z'::timestamptz AS noflop_fix_at
)
SELECT
  h.hand_id,
  h.table_id,
  h.played_at::timestamptz AS played_at,
  h.gross_pot_bb,
  h.rake_bb,
  'current_hand_missing_analytics_history' AS anomaly
FROM online_hands h
LEFT JOIN jj_hand_history hh ON hh.hand_id=h.hand_id
CROSS JOIN policy p
WHERE h.played_at::timestamptz >= p.noflop_fix_at
  AND hh.hand_id IS NULL
ORDER BY h.played_at::timestamptz, h.hand_id;

-- Current-policy hard bounds, independent of hand-history availability.
WITH policy AS (
  SELECT '2026-09-14T16:17:08.642886Z'::timestamptz AS rake_5_3_at
)
SELECT
  h.hand_id,
  h.table_id,
  h.played_at::timestamptz AS played_at,
  h.gross_pot_bb,
  h.rake_bb,
  'current_rake_bound_violation' AS anomaly
FROM online_hands h
CROSS JOIN policy p
WHERE h.played_at::timestamptz >= p.rake_5_3_at
  AND (h.rake_bb < 0 OR h.rake_bb > 3 OR h.rake_bb > h.gross_pot_bb)
ORDER BY h.played_at::timestamptz, h.hand_id;

-- No Flop No Drop audit.
-- Current rows returned here are defects. Pre-fix rows identify historical
-- records that may need a separate repair decision, but this audit never writes.
WITH policy AS (
  SELECT '2026-09-14T17:43:56.661173Z'::timestamptz AS noflop_fix_at
),
rollup AS (
  SELECT
    h.hand_id,
    h.table_id,
    h.played_at::timestamptz AS played_at,
    h.gross_pot_bb,
    h.rake_bb,
    hh.reached_street,
    hh.player_count,
    COUNT(r.id) AS result_count,
    COALESCE(SUM(r.result_bb),0) AS sum_result_bb,
    p.noflop_fix_at
  FROM online_hands h
  JOIN jj_hand_history hh ON hh.hand_id=h.hand_id
  LEFT JOIN online_hand_results r ON r.hand_id=h.hand_id
  CROSS JOIN policy p
  WHERE hh.reached_street='preflop'
  GROUP BY
    h.hand_id,h.table_id,h.played_at,h.gross_pot_bb,h.rake_bb,
    hh.reached_street,hh.player_count,p.noflop_fix_at
)
SELECT
  *,
  CASE WHEN played_at >= noflop_fix_at
       THEN 'current_noflop_violation'
       ELSE 'legacy_noflop_metadata_gap'
  END AS anomaly
FROM rollup
WHERE rake_bb <> 0
   OR gross_pot_bb <= 0
   OR ABS(sum_result_bb + rake_bb) > 0.011
   OR (player_count IS NOT NULL AND result_count <> player_count)
ORDER BY played_at, hand_id;

-- Historical exposure window for the former uncalled-contribution bug.
-- These rows are NOT automatically wrong. Aggregate online_hands data cannot
-- prove that a hand contained an unmatched top contribution, so they are listed
-- for targeted reconstruction only if a historical repair is ever desired.
WITH policy AS (
  SELECT '2026-09-14T15:59:55.992406Z'::timestamptz AS uncalled_fix_at
)
SELECT
  h.hand_id,
  h.table_id,
  h.played_at::timestamptz AS played_at,
  h.gross_pot_bb,
  h.rake_bb,
  hh.reached_street,
  'legacy_uncalled_rake_risk_window' AS audit_note
FROM online_hands h
LEFT JOIN jj_hand_history hh ON hh.hand_id=h.hand_id
CROSS JOIN policy p
WHERE h.played_at::timestamptz < p.uncalled_fix_at
ORDER BY h.played_at::timestamptz, h.hand_id;

-- Compact anomaly summary. Zero is expected for all "current_*" and structural
-- categories. Legacy categories are informational and may be non-zero.
WITH policy AS (
  SELECT
    '2026-09-14T15:59:55.992406Z'::timestamptz AS uncalled_fix_at,
    '2026-09-14T16:17:08.642886Z'::timestamptz AS rake_5_3_at,
    '2026-09-14T17:43:56.661173Z'::timestamptz AS noflop_fix_at
),
rollup AS (
  SELECT
    h.hand_id,
    h.table_id,
    h.played_at::timestamptz AS played_at,
    h.gross_pot_bb,
    h.rake_bb,
    h.voided,
    hh.reached_street,
    hh.player_count,
    COUNT(r.id) AS result_count,
    COALESCE(SUM(r.result_bb),0) AS sum_result_bb
  FROM online_hands h
  LEFT JOIN online_hand_results r ON r.hand_id=h.hand_id
  LEFT JOIN jj_hand_history hh ON hh.hand_id=h.hand_id
  GROUP BY
    h.hand_id,h.table_id,h.played_at,h.gross_pot_bb,h.rake_bb,h.voided,
    hh.reached_street,hh.player_count
),
formula AS (
  SELECT
    x.*,
    CASE
      WHEN x.reached_street='preflop' THEN 0::numeric
      WHEN x.played_at >= p.rake_5_3_at
        THEN LEAST(FLOOR(x.gross_pot_bb * 5) / 100, 3::numeric)
      ELSE LEAST(FLOOR(x.gross_pot_bb * 10) / 100, 5::numeric)
    END AS expected_rake_bb
  FROM rollup x
  CROSS JOIN policy p
  WHERE x.reached_street IS NOT NULL
),
summary AS (
  SELECT 'fixed_table_policy_violation' AS check_name, COUNT(*)::bigint AS finding_count
  FROM tables
  WHERE state_json::jsonb ? 'rake_percent'
    AND (
      COALESCE(NULLIF(state_json::jsonb->>'rake_percent','')::numeric, -1) <> 0.05
      OR COALESCE(NULLIF(state_json::jsonb->>'rake_cap','')::numeric, -1)
         <> COALESCE(NULLIF(state_json::jsonb->>'big_blind','')::numeric, 0) * 3
    )
  UNION ALL
  SELECT 'orphan_result', COUNT(*) FROM online_hand_results r
    LEFT JOIN online_hands h ON h.hand_id=r.hand_id WHERE h.hand_id IS NULL
  UNION ALL
  SELECT 'points_mismatch', COUNT(*) FROM online_hand_results
    WHERE ABS(points - ROUND(result_bb * 3,2)) > 0.001
  UNION ALL
  SELECT 'hand_conservation_or_completeness', COUNT(*) FROM rollup
    WHERE gross_pot_bb < 0 OR rake_bb < 0
       OR ABS(sum_result_bb + rake_bb) > 0.011
       OR (player_count IS NOT NULL AND result_count <> player_count)
  UNION ALL
  SELECT 'rake_formula_violation', COUNT(*) FROM formula
    WHERE ABS(rake_bb - expected_rake_bb) > 0.001
  UNION ALL
  SELECT 'current_rake_bound_violation', COUNT(*) FROM rollup x CROSS JOIN policy p
    WHERE x.played_at >= p.rake_5_3_at
      AND (x.rake_bb < 0 OR x.rake_bb > 3 OR x.rake_bb > x.gross_pot_bb)
  UNION ALL
  SELECT 'current_missing_analytics_history', COUNT(*) FROM rollup x CROSS JOIN policy p
    WHERE x.played_at >= p.noflop_fix_at AND x.reached_street IS NULL
  UNION ALL
  SELECT 'current_noflop_violation', COUNT(*) FROM rollup x CROSS JOIN policy p
    WHERE x.played_at >= p.noflop_fix_at AND x.reached_street='preflop'
      AND (
        x.rake_bb <> 0 OR x.gross_pot_bb <= 0
        OR ABS(x.sum_result_bb + x.rake_bb) > 0.011
        OR (x.player_count IS NOT NULL AND x.result_count <> x.player_count)
      )
  UNION ALL
  SELECT 'legacy_noflop_metadata_gap', COUNT(*) FROM rollup x CROSS JOIN policy p
    WHERE x.played_at < p.noflop_fix_at AND x.reached_street='preflop'
      AND (
        x.rake_bb <> 0 OR x.gross_pot_bb <= 0
        OR ABS(x.sum_result_bb + x.rake_bb) > 0.011
        OR (x.player_count IS NOT NULL AND x.result_count <> x.player_count)
      )
  UNION ALL
  SELECT 'legacy_uncalled_risk_window_hands', COUNT(*) FROM rollup x CROSS JOIN policy p
    WHERE x.played_at < p.uncalled_fix_at
)
SELECT * FROM summary ORDER BY check_name;

ROLLBACK;
