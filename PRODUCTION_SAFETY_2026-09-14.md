# Production safety rollout — 2026-09-14

## Observed state before this PR

- main: `7d3593c707f2764b904ca46fe7c4a649adca464e`, `protected=false`.
- Both Render services: `autoDeploy=yes`, `autoDeployTrigger=commit`, branch main.
- Existing commit checks succeeded, but two unrelated jobs were both named `smoke`.
- Render's read-only PostgreSQL connector failed with unexpected EOF / SSL-TLS required. No production SQL ran successfully and no production data was changed.

## 1. Protect main before merging

This PR gives the complete CI job the unique check name `production-release-gate` and the hand-history job `hand-history-visibility`. The complete CI job already executes `python production_release_gate.py`, PostgreSQL integration and the remaining regression suite. The four required jobs have unconditional pull_request/main triggers and no path filters.

After this PR's checks have reported their new names, an administrator can apply the reviewed payload from the repository root:

```sh
gh api --method PUT repos/sanoken0201-beep/jj-arena-live/branches/main/protection --input tools/main-protection.json
gh api repos/sanoken0201-beep/jj-arena-live/branches/main/protection
```

Required checks: `production-release-gate`, `phase4b`, `auth-security`, `point-ledger-precision`, all from the verified GitHub Actions app ID 15368. Require the branch to be current, require PRs, apply to administrators, prohibit force pushes/deletion, and resolve review conversations. Zero approving reviews permits a single-maintainer workflow while retaining the PR and CI requirements. Do not add bypass actors. Check existing rulesets separately before replacing any protection configuration; this payload was prepared against the observed unprotected state.

The connector used for this work does not expose protection writes. The payload is a proposal, not proof of enforcement.

## 2. Gate both existing Render services before merging

Set Settings → Auto-Deploy → **After CI Checks Pass** on both:

- https://dashboard.render.com/web/srv-dae3b6n40ujc73dkqk1g/settings
- https://dashboard.render.com/web/srv-dae52bou01pc73d4npjg/settings

Equivalent authenticated Render API mutation: PATCH `/v1/services/{serviceId}` with `tools/render-autodeploy.json`. Read back BOTH services and confirm `branch=main`, `autoDeployTrigger=checksPass`.

`render.yaml` records this value for the existing backend Blueprint. It does not manage the proxy service. Editing YAML alone is not evidence that either live service setting changed. The connector does not expose this service-setting mutation.

After enforcement: PR checks succeed → merge into current main → main checks succeed → Render auto-deploy. Do not manually trigger a deploy or use a deploy hook to bypass this sequence.

Render treats success, neutral and skipped as passing. Keep required jobs unconditional, keep skip directives out of release commits, and inspect the four required conclusions for actual success before merging. Sources: https://render.com/docs/deploys and https://render.com/docs/blueprint-spec#autodeploytrigger

## 3. Read-only production point audit

Run `tools/point_integrity_audit.sql` from an authorized TLS-capable connection. It uses a repeatable-read, read-only transaction, a 15-second statement timeout, and rollback. Do not import the production application just to audit: imports can execute schema migrations.

Validate NUMERIC(12,2), transaction totals, orphan records, credit/collection signs, quiz +10 rewards, daily-answer/reward pairing, reversal amounts/owners/dates, duplicate reversals, and duplicate active ranking mappings. Historical non-10 rewards require investigation rather than automatic correction.

The final query calculates expected fall ranking components for 2026-09-01 through 2027-04-01. Compare every row with authenticated `/api/rankings?season=fall` and administrator account `season_points`. Compare during a quiet period or account for writes between snapshots. A computed expectation is not an independent comparison with the live display. `arena_chips` and `xp` are separate from ranking points; do not compare them to ledger totals.

New credit/collection/quiz behavior should be exercised on disposable data, not by issuing real production points. Record production evidence separately; this PR contains no successful production-data audit result.

## 4. Monitor warnings

- API P95 above 500ms: yellow 注意; above 1000ms: red 警告. Equality at 500/1000 stays in the lower band.
- DB pool current waiting above zero: yellow 注意.
- 24-hour error count above zero: yellow 注意. Historical retained errors do not cause a permanent warning.
- Missing latency samples/metrics: 未計測, not a zero/healthy value.
- WebSocket count remains informational: zero connected clients alone does not imply failure.
- Failed refresh replaces system metrics with an explicit unknown-state warning.
- Labels accompany colors; admin asset version increments to invalidate cached JS/CSS.

`materialized_v1244` is unchanged. No game timings or connection-pool parameters are modified.
