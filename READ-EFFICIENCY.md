# Result-preserving read reduction

Baseline: main `1af07586de5a50b35d66037bb4dab07c80060254`.
The materialized_v1244 source/manifest, game rules, scheduler intervals, point
writes, rendering and access checks are unchanged. No paid service or plan change.

## Implemented

| Path | Before | After |
|---|---|---|
| Immediate broadcast after save | One additional table SELECT and private-state JSON fingerprint | No additional table SELECT; revision and structural comparison |
| Six-player settlement | Six individual user SELECTs | One user SELECT with six bound IDs |
| GET /api/me | Auth JOIN plus user SELECT | Auth JOIN only; same seven public fields |
| Home core data | Four HTTP requests and four auth queries | One request and one auth query |
| Points dashboard data | Two HTTP requests and two auth queries | One request and one auth query |

The aggregate endpoints execute the original read endpoint functions with a
request-local bound DB connection. Queries, ordering, filters, ranking arithmetic
and returned fields remain owned by the original functions. They do not cache
responses. Old endpoints remain accessible with their existing permissions.
The browser calls the old group only if the aggregate request fails or returns
an invalid bundle. A subsequent refresh always fetches new data.

Settlement also delegates the original function: a connection adapter replaces
only its individual name lookup with a lazily populated map. Its ranking-name
fallback, inserts, transaction boundaries and arithmetic are unchanged.

## Broadcast freshness boundaries

Every ordinary load_table still reads the DB. After a successful save/read, an
owned copy is held with a per-table generation. A ticket permits reuse only by
the same asyncio task in the same event-loop turn. Yielding, a missing snapshot,
another generation, or a failed save forces the original DB load. Startup and
maintenance thus do not rely on an indefinitely valid process cache. The former
load-time state repair still runs before broadcast and persists repairs first.
Private state is never sent directly: every recipient still passes through
public_state(state, user_id). No state frame or delay is throttled/coalesced.
No-op saves retain the previous chat-only behavior via structural equality.

## Validation

smoke_test_read_efficiency.py compares real old/new API payloads and SQL counts,
settlement return values and persisted rows under savepoint rollback, six
personalized frames, card privacy, no-op saves, invalidation, child-task/await
boundaries, and failed DB commit rollback. PostgreSQL tests create a disposable
database only on explicitly allowed localhost/127.0.0.1 CI hosts. SQLite uses a
temporary database. smoke_test_read_bundle.js checks success/failure/invalid and
sign-out request counts. Existing lifecycle/timeout, parity, UX and security gates
remain required. Client assets and service worker advance together to v71.

## Priority 6: intentionally no SQL/index mutation

The canonical rankings query uses substr(date,1,7). PointEntry.date is a string,
and its existing season validation permits a value such as `2026-10`.
For three rows dated `2026-10`, `2026-10-01`, and `2026-10-31T23:59` with points
1, 2, 3, the October legacy sum is 6. A range beginning `2026-10-01` produces 5.
Changing input validation would be a separate behavior change, so this predicate
is preserved.

An isolated SQLite EXPLAIN shows the existing (name,date) index scans in grouping
order. A hypothetical (date,name) index enables a date-range search but requires
a temporary GROUP BY B-tree. This is a tradeoff, not evidence of a net production
benefit at the stated small scale. Production read-only count/EXPLAIN/index
inspection was attempted through Render but failed during connector TLS setup;
no database access rule was changed. No index was created in production and no
INSERT/UPDATE overhead was added.

These are query/request reductions, not a claim of a measured percentage speedup
or a change to the supported player count.
