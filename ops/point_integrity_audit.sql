-- Run with psql on the production database; no application imports or writes.
-- Output contains member identifiers: keep it private.
\set ON_ERROR_STOP on
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '15s';
SELECT current_timestamp AS snapshot_time;
SELECT data_type,numeric_precision,numeric_scale
FROM information_schema.columns
WHERE table_schema='public' AND table_name='point_ledger' AND column_name='amount';
-- Every anomaly result below must be empty; investigate, do not auto-correct.
SELECT l.id, 'orphan_user' AS anomaly FROM point_ledger l
LEFT JOIN users u ON u.id=l.user_id WHERE u.id IS NULL;
SELECT id,kind,amount FROM point_ledger
WHERE amount::text IN ('NaN','Infinity','-Infinity')
 OR (kind='quiz_reward' AND amount<>10)
 OR (kind='credit' AND amount<=0) OR (kind='collection' AND amount>=0)
 OR (kind='sitngo_entry' AND amount>=0)
 OR (kind IN ('sitngo_refund','sitngo_prize') AND amount<=0)
 OR kind NOT IN ('quiz_reward','credit','collection','reversal','sitngo_entry','sitngo_refund','sitngo_prize');
SELECT r.id,'invalid_reversal' AS anomaly FROM point_ledger r
LEFT JOIN point_ledger original ON original.id=r.reversal_of
WHERE r.kind='reversal' AND (original.id IS NULL
 OR original.kind NOT IN ('credit','collection')
 OR r.user_id<>original.user_id OR r.amount<>-original.amount
 OR r.effective_at<>original.effective_at);
SELECT r.id,'invalid_sitngo_refund' AS anomaly FROM point_ledger r
LEFT JOIN point_ledger original ON original.id=r.reversal_of
WHERE r.kind='sitngo_refund' AND (original.id IS NULL OR original.kind<>'sitngo_entry'
 OR r.user_id<>original.user_id OR r.amount<>-original.amount);

SELECT p.event_id,p.user_id,'sitngo_payment_ledger_mismatch' AS anomaly
FROM sitngo_payments p LEFT JOIN point_ledger l ON l.id=p.entry_tx
WHERE l.id IS NULL OR l.user_id<>p.user_id OR l.kind<>'sitngo_entry'
 OR l.amount*100<>-p.fee_cents;

SELECT p.event_id,p.user_id,'sitngo_refund_missing_or_mismatch' AS anomaly
FROM sitngo_payments p
LEFT JOIN point_ledger r ON r.reversal_of=p.entry_tx AND r.kind='sitngo_refund'
WHERE p.refunded=1 AND (r.id IS NULL OR r.user_id<>p.user_id OR r.amount*100<>p.fee_cents);

SELECT reg.event_id,reg.user_id,'sitngo_active_registration_without_escrow' AS anomaly
FROM sitngo_registrations reg
JOIN sitngo_terms t ON t.event_id=reg.event_id
LEFT JOIN sitngo_payments p
 ON p.event_id=reg.event_id AND p.user_id=reg.user_id AND p.refunded=0
WHERE reg.status IN ('registered','active') AND t.fee_cents>0 AND p.user_id IS NULL;

SELECT p.event_id,p.user_id,'sitngo_free_event_has_active_escrow' AS anomaly
FROM sitngo_payments p JOIN sitngo_terms t ON t.event_id=p.event_id
WHERE t.fee_cents=0 AND p.refunded=0;

WITH settlement_awards AS (
 SELECT s.event_id,SUM((award.value)::numeric) AS award_cents
 FROM sitngo_settlements s
 CROSS JOIN LATERAL jsonb_each_text(s.awards_json::jsonb) AS award
 GROUP BY s.event_id
), escrow AS (
 SELECT event_id,SUM(fee_cents)::numeric AS escrow_cents
 FROM sitngo_payments WHERE refunded=0 GROUP BY event_id
), prizes AS (
 SELECT s.event_id,COALESCE(SUM(l.amount)*100,0)::numeric AS prize_cents
 FROM sitngo_settlements s
 LEFT JOIN point_ledger l
   ON l.kind='sitngo_prize' AND l.id LIKE 'sng-prize-'||s.event_id||'-%'
 GROUP BY s.event_id
)
SELECT s.event_id,'sitngo_settlement_mismatch' AS anomaly
FROM settlement_awards s
LEFT JOIN escrow e USING(event_id)
LEFT JOIN prizes p USING(event_id)
WHERE s.award_cents<>COALESCE(e.escrow_cents,0)
 OR s.award_cents<>COALESCE(p.prize_cents,0);
SELECT reversal_of,count(*) FROM point_ledger WHERE reversal_of IS NOT NULL
GROUP BY reversal_of HAVING count(*)>1;
SELECT q.id,'quiz_ledger_mismatch' AS anomaly FROM quiz_daily_answers q
LEFT JOIN point_ledger l ON l.id='dq3-'||q.id
WHERE (q.answer IS NOT NULL AND (q.reward_awarded<>10 OR l.id IS NULL
 OR l.kind<>'quiz_reward' OR l.amount<>10 OR l.user_id<>q.user_id))
 OR (q.answer IS NULL AND (q.reward_awarded<>0 OR l.id IS NOT NULL));
SELECT l.id,'orphan_daily_quiz_ledger' AS anomaly FROM point_ledger l
LEFT JOIN quiz_daily_answers q ON l.id='dq3-'||q.id
WHERE l.id LIKE 'dq3-%' AND q.id IS NULL;
SELECT COALESCE(NULLIF(ranking_name,''),name) AS ranking_name,count(*)
FROM users WHERE COALESCE(disabled,0)=0 AND deleted_at IS NULL
GROUP BY COALESCE(NULLIF(ranking_name,''),name) HAVING count(*)>1;
-- All-time ledger reconciliation (not the complete season balance).
SELECT kind,count(*),sum(amount) FROM point_ledger GROUP BY kind ORDER BY kind;
SELECT u.id,COALESCE(sum(l.amount),0) AS ledger_total
FROM users u LEFT JOIN point_ledger l ON l.user_id=u.id GROUP BY u.id ORDER BY u.id;
-- Expected fall ranking balances. Compare every name/component to GET /api/rankings
-- and admin users' season_points using the same season, accounting for live updates.
-- No separate stored account balance is present in the inspected implementation.
WITH club AS (
 SELECT name,round(sum(points)::numeric,2) AS points FROM entries
 WHERE name<>'運営調整' AND date>='2026-09-01' AND date<'2027-04-01' GROUP BY name
), online AS (
 SELECT r.ranking_name AS name,round(sum(r.points)::numeric,2) AS points
 FROM online_hand_results r JOIN online_hands h ON h.hand_id=r.hand_id
 WHERE COALESCE(h.voided,0)=0 AND h.played_at>='2026-09-01' AND h.played_at<'2027-04-01'
 GROUP BY r.ranking_name
), ledger AS (
 SELECT COALESCE(NULLIF(u.ranking_name,''),u.name) AS name,
 sum(l.amount) AS points,
 sum(CASE WHEN l.kind='quiz_reward' THEN l.amount ELSE 0 END) AS quiz_points,
 sum(CASE WHEN l.kind IN ('credit','collection','reversal') THEN l.amount ELSE 0 END) AS admin_points
 FROM point_ledger l JOIN users u ON u.id=l.user_id
 WHERE l.effective_at>='2026-09-01' AND l.effective_at<'2027-04-01'
 GROUP BY COALESCE(NULLIF(u.ranking_name,''),u.name)
), names AS (SELECT name FROM club UNION SELECT name FROM online UNION SELECT name FROM ledger)
SELECT n.name,COALESCE(c.points,0) AS club_points,COALESCE(o.points,0) AS online_points,
 COALESCE(l.points,0) AS ledger_points,COALESCE(l.quiz_points,0) AS quiz_points,
 COALESCE(l.admin_points,0) AS admin_points,
 COALESCE(c.points,0)+COALESCE(o.points,0)+COALESCE(l.points,0) AS expected_season_points
FROM names n LEFT JOIN club c USING(name) LEFT JOIN online o USING(name) LEFT JOIN ledger l USING(name)
ORDER BY expected_season_points DESC,n.name;
ROLLBACK;
