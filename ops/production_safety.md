# Production safety rollout — 2026-09-14

Status: prepared, NOT applied to live GitHub/Render configuration. Do not merge this PR before steps 1–2. No production data was modified.

## 1. Protect main

GitHub Settings → Branches → protection for `main`:

- Require a pull request before merging (0 approving reviews is sufficient for a solo maintainer).
- Require status checks to pass and require the branch to be up to date.
- Required checks from GitHub Actions: `production release gate`, `phase4b`, `auth-security`, `point-ledger-precision`.
- Apply rules to administrators / do not allow bypassing; no bypass actors.
- Disable force pushes and deletions.

The CI release job previously shared the name `smoke` with Participant Hand History Visibility. This PR gives it the unique name `production release gate`. Select this new check after its PR run has registered it; do not substitute the unrelated `smoke`. The entire CI job must succeed, including `python production_release_gate.py`.

Verify by reading main protection after saving. Expected: protected=true, strict=true, enforce_admins=true, PR requirement present, all four checks required. Branch protection is a GitHub setting; merging repository files does not apply it.

https://github.com/sanoken0201-beep/jj-arena-live/settings/branches

## 2. Gate both Render services

Set Auto-Deploy → **After CI Checks Pass** for BOTH services, keeping branch main:

- https://dashboard.render.com/web/srv-dae3b6n40ujc73dkqk1g/settings
- https://dashboard.render.com/web/srv-dae52bou01pc73d4npjg/settings

Read back `autoDeployTrigger=checksPass` for both services before merging. This PR also records checksPass in the existing live-service Blueprint. The club proxy is not currently managed by that file; do not create a duplicate service by adding a new Blueprint.

With strict main protection: PR checks pass → merge to main → main checks pass → automatic production deploy. Manual deploys/deploy hooks can bypass Render's automatic trigger policy; do not use them for unverified commits. Existing in-flight deployments are not cancelled by changing this setting.

Official docs: https://render.com/docs/deploys and https://render.com/docs/blueprint-spec

## 3. Read-only point audit

The connector failed before executing SQL: unexpected EOF / SSL/TLS required. Production migration status and all data consistency checks remain UNVERIFIED. External access was not broadened to work around this error.

Run `psql "$DATABASE_URL" -f ops/point_integrity_audit.sql` from an authorized environment with database connectivity. The script uses one repeatable-read read-only transaction and 15-second statement timeouts. It performs no application imports/migrations.

Confirm NUMERIC(12,2), empty anomaly sets, and compare expected season balances by name/component against authenticated `/api/rankings` and admin users' `season_points`. Ranking = club + non-voided online + ledger; ledger alone is not the user balance. Legacy quiz ledger amounts are checked; daily quiz answers are cross-checked one-to-one using dq3 IDs. Historical pre-migration rounding loss cannot be proven absent without a before-migration snapshot. Run isolated quiz/admin integration regressions; do not create fake rewards in production.

## 4. Monitoring

Dashboard warnings: P95 >500ms yellow, >1000ms red; waiting DB requests yellow; errors in the last 24h yellow. Color is accompanied by text. Missing data is marked unmeasured, failed refreshes explicitly mark old values stale. WS counts remain informational because counts alone do not establish connection failures. Existing 60-second refresh is retained; no extra requests or game timing changes. Canonical materialized_v1244 is untouched.
