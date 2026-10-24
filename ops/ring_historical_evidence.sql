-- Administrator-only forensic inventory. No user IDs, cards or raw snapshots.
-- Run separately from application startup: importing app executes migrations.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '20s';
SELECT key, applied_at FROM app_migrations
WHERE key='2026-09-10-clear-existing-online-results';

WITH missing AS (
 SELECT h.hand_id,h.played_at,hh.player_count,hh.partial_capture,
        hh.completed_at,hh.reached_street
 FROM online_hands h
 LEFT JOIN jj_hand_history hh ON hh.hand_id=h.hand_id
 WHERE NOT EXISTS (SELECT 1 FROM online_hand_results r WHERE r.hand_id=h.hand_id)
), evidence AS (
 SELECT m.*,
   (SELECT COUNT(*) FROM jj_hand_players p WHERE p.hand_id=m.hand_id) AS player_rows,
   (SELECT COUNT(*) FROM jj_hand_players p WHERE p.hand_id=m.hand_id
      AND p.ending_stack IS NOT NULL AND p.net_bb IS NOT NULL) AS completed_player_rows,
   (SELECT COUNT(*) FROM jj_hand_snapshots s WHERE s.hand_id=m.hand_id) AS snapshots,
   (SELECT applied_at::timestamptz FROM app_migrations
      WHERE key='2026-09-10-clear-existing-online-results') AS cleanup_at
 FROM missing m
)
SELECT (played_at::timestamptz AT TIME ZONE 'Asia/Tokyo')::date AS played_day_jst,
 CASE WHEN cleanup_at IS NULL THEN 'marker_absent'
      WHEN played_at::timestamptz <= cleanup_at THEN 'before_or_at_cleanup'
      ELSE 'after_cleanup' END AS cleanup_window,
 player_count,partial_capture,reached_street,
 COUNT(*) AS missing_hands,
 COUNT(*) FILTER (WHERE completed_at IS NOT NULL) AS completed_history,
 COUNT(*) FILTER (WHERE player_rows=player_count AND player_count>0) AS matching_player_rows,
 COUNT(*) FILTER (WHERE completed_player_rows=player_count AND player_count>0) AS complete_player_outcomes,
 COUNT(*) FILTER (WHERE snapshots>0) AS hands_with_snapshots
FROM evidence
GROUP BY 1,2,3,4,5 ORDER BY 1,2,3,4,5;
ROLLBACK;
-- A cleanup-window match is a candidate explanation, NOT proof of deletion.
-- Complete outcome counts are NOT authorization/evidence sufficient for repair.
