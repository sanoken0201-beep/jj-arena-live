-- Execute with psql -X "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tools/point_integrity_audit.sql
-- No application import: importing the application can run startup migrations.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '15s';
SELECT CURRENT_TIMESTAMP AS audited_at;
SELECT data_type,numeric_precision,numeric_scale
FROM information_schema.columns
WHERE table_schema='public' AND table_name='point_ledger' AND column_name='amount';

SELECT kind,COUNT(*) AS transactions,COALESCE(SUM(amount),0) AS total
FROM point_ledger GROUP BY kind ORDER BY kind;

SELECT
  COUNT(*) FILTER (WHERE u.id IS NULL) AS orphan_ledger_rows,
  COUNT(*) FILTER (WHERE l.kind='credit' AND l.amount<=0) AS invalid_credits,
  COUNT(*) FILTER (WHERE l.kind='collection' AND l.amount>=0) AS invalid_collections,
  COUNT(*) FILTER (WHERE l.kind='quiz_reward' AND l.amount<>10) AS non_ten_point_rewards,
  COUNT(*) FILTER (WHERE l.amount IS NULL OR l.amount::text IN ('NaN','Infinity','-Infinity')) AS invalid_amounts
FROM point_ledger l LEFT JOIN users u ON u.id=l.user_id;

SELECT COUNT(*) AS daily_reward_mismatches
FROM quiz_daily_answers a FULL JOIN point_ledger l ON l.id='dq3-'||a.id
WHERE (a.reward_awarded=10 AND (l.id IS NULL OR l.amount<>10 OR l.user_id<>a.user_id OR l.kind<>'quiz_reward'))
   OR (l.id LIKE 'dq3-%' AND (a.id IS NULL OR a.reward_awarded<>10 OR a.answered_at IS NULL));

SELECT COUNT(*) AS invalid_reversals FROM point_ledger r
LEFT JOIN point_ledger o ON o.id=r.reversal_of
WHERE r.kind='reversal' AND (o.id IS NULL OR r.amount<>-o.amount OR r.user_id<>o.user_id OR r.effective_at<>o.effective_at);
SELECT COUNT(*) AS duplicate_reversal_targets FROM (
  SELECT reversal_of FROM point_ledger WHERE reversal_of IS NOT NULL
  GROUP BY reversal_of HAVING COUNT(*)>1
) duplicates;
SELECT COUNT(*) AS duplicate_active_ranking_mappings FROM (
  SELECT COALESCE(NULLIF(ranking_name,''),name) FROM users
  WHERE COALESCE(disabled,0)=0 AND deleted_at IS NULL
  GROUP BY COALESCE(NULLIF(ranking_name,''),name) HAVING COUNT(*)>1
) duplicates;

-- This is the expected fall ranking, NOT a claim that the live API was compared.
-- There is no separate point balance column. arena_chips and xp are different units.
WITH contributions AS (
  SELECT name,SUM(points)::numeric AS club,0::numeric AS online,0::numeric AS ledger
  FROM entries WHERE name<>'運営調整' AND date>='2026-09-01' AND date<'2027-04-01' GROUP BY name
  UNION ALL
  SELECT r.ranking_name,0,SUM(r.points),0 FROM online_hand_results r
  JOIN online_hands h ON h.hand_id=r.hand_id
  WHERE COALESCE(h.voided,0)=0 AND h.played_at>='2026-09-01' AND h.played_at<'2027-04-01' GROUP BY r.ranking_name
  UNION ALL
  SELECT COALESCE(NULLIF(u.ranking_name,''),u.name),0,0,SUM(l.amount)
  FROM point_ledger l JOIN users u ON u.id=l.user_id
  WHERE l.effective_at>='2026-09-01' AND l.effective_at<'2027-04-01'
  GROUP BY COALESCE(NULLIF(u.ranking_name,''),u.name)
)
SELECT name,ROUND(SUM(club),2) AS club_points,ROUND(SUM(online),2) AS online_points,
       ROUND(SUM(ledger),2) AS ledger_points,
       ROUND(ROUND(SUM(club),2)+ROUND(SUM(online),2)+ROUND(SUM(ledger),2),2) AS expected_season_points
FROM contributions GROUP BY name ORDER BY expected_season_points DESC,name;
ROLLBACK;
