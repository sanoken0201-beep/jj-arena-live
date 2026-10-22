# MDA production rollout / rollback runbook

**State: preparation only, not authorized for deployment.** Last externally reviewed 2026-10-16 JST. Confirm live status again before executing.

## Known environment

- Repository: sanoken0201-beep/jj-arena-live. Web app: jj-arena-live on Render. Production branch: main.
- Render setting: autoDeploy=yes; autoDeployTrigger=checksPass. A merge to main can cause an immediate production deployment on the single-instance web service, interrupting an in-progress game. Do NOT merge a draft PR as source-control housekeeping.
- At verification the last live deploy was dep-db69bnqvcj2c73fconb0 at commit 98f0ca2cfcabd7f02f846d4215abdea3e00b2eaf. This is a historical reference, **not** an instruction to roll back to that SHA without checking its suitability at release time.
- Database is jj-arena-db. Its external IP allowlist is empty, so the direct Render SQL connector is blocked. Do not open external connectivity as a workaround. No live historical MDA counts have yet been obtained.
- Draft PRs #200 through #208 are stacked. PR checks can prove code quality but cannot prove production DB coverage or valid privacy assumptions.

## Stage A: code deployment with feature OFF

The administrator grid API requires exact environment variable JJ_MDA_ADMIN_ENABLED=1 before returning any cached population data. Unset, 0, false, or an empty value produces the normal not_ready response without performing any cache-table query. Normal admin-only authentication still applies before this check. The new code installs no automatic background scan.

1. Reconfirm current main SHA, live Render deploy ID/SHA and any other merged changes. Prepare an explicit rollback owner and low-traffic deployment window.
2. Review all code and PR dependencies, GitHub CI, security, Ring/Sit&Go, auth, mobile/browser and production release gate. Require success on the exact candidate SHA.
3. Coordinate integration carefully: merging each of eight PRs separately into an auto-deploy-enabled main can trigger eight production deploys. Plan a single reviewed integration/release strategy where feasible and avoid disrupting a real game.
4. Keep JJ_MDA_ADMIN_ENABLED unset. Verify the new administrator grid returns not_ready, the non-admin user receives 403, unauthenticated receives 401, and Ring/Sit&Go actions and points work.
5. Confirm active Render deploy SHA and health state. Any unexpected game regression is NO-GO for further stages.

## Stage B: read-only historical data inspection

Run only from a reviewed, authorized Render internal host using the existing private DATABASE_URL. Never copy this secret into the chat or a third-party runner.

1. Run python mda_coverage_gate.py, which uses only anonymous SQL aggregates and a five-second per-query timeout.
2. Verify **both** jj-table-a and jj-table-b appear in the official Ring coverage; all administrator/member player roles enter the aggregate without any role predicate; 2–6 dealt-in populations are separate. Sit&Go is a separate source.
3. Check fully captured hand rates, distinct players, missing hole-card rows, and available action records. Coarse aggregates do NOT establish sufficient 169-class RFI sample sizes.
4. Inspect SQL query plans, load and timeouts on the starter PostgreSQL instance. Small bounded tests precede any full scan. Full historical scans are expensive even if read-only.
5. Require a clear operator go/no-go decision based on actual anonymized results, which are not yet available.

## Stage C: separate opt-in publisher and display activation

- Only after Stage B: python mda_snapshot_cache.py --permit-primary-scan performs a full historical read-only dry run. The --publish switch performs atomic publication of sanitized 13x13 grids and is intentionally separate.
- Perform large scans off-peak, ideally on a suitable isolated worker or replica, NEVER from a game request or WebSocket. Ensure capacity and reasonable statement timeouts.
- A previously published Table-A-only Ring baseline is NOT comparable with the newer two-table Ring population; create a new baseline for future revisions.
- Inspect cache table contents, privacy thresholds, cohort isolation, and an authenticated administrator GET before enabling the UI. Unknown is not a 0% action frequency; a guess is not an observed raise.
- Only after review enable JJ_MDA_ADMIN_ENABLED=1 in Render. Environment changes may trigger a redeploy; verify the resulting SHA and live table health. Member-facing access is still prohibited.
- No recurring Cron or additional service is provisioned by these PRs. Creating one needs separate capacity/cost approval and a scheduled off-peak window.

## Rollback

1. Fastest scope reduction: set JJ_MDA_ADMIN_ENABLED=0 or remove the variable, then verify no cached population data is returned even to an administrator. A Render environment change may itself redeploy.
2. On any gameplay or login regression, revert the offending main changes through a reviewed recovery PR or restore a known-good Render deploy with operator oversight. Because main auto-deploys, a deploy-only rollback is not a permanent fix unless GitHub main is reconciled.
3. Verify game actions, Sit&Go registration/results, ranking and points, authentication, static manifest parity, health endpoint, error rate and the live deploy SHA.
4. Do not delete historical hands, tournament/points tables, or roll back the whole production database just to undo MDA. Keep the independent sanitized cache table isolated.
5. Keep logs/aggregated metrics for diagnosis but NEVER export player names, user IDs, historical exact hole cards or credentials.

## Release evidence required

Record explicit deployment approval, low-traffic release window, confirmed main and live SHAs, approved rollback owner, successful CI, data coverage by both Ring tables, accepted/rejected audit counts, measured DB headroom, activated feature-flag state and post-release health checks.

Automated tests cover the default-disabled admin data gate, no DB hit when disabled, no opponent-specific disclosures, strict size/position scopes and no all-history scanner imports from the web request path. These tests do not constitute a live production performance benchmark.

**No merge, Render deploy, data scan or job provisioning is authorized by this runbook alone.**
