# Quiz, WebSocket and historical Ring investigation

Baseline: main 66d0870e. The operator approved the GitHub branch upload and
read-only investigation in the confirmed Render workspace. Production logs were
read; direct DB access was blocked by an empty external IP allowlist. No deployment,
point repair, access-policy change or historical data modification was performed.

## Quiz 401

The compiled browser has six question request call sites. Header
`X-JJ-Quiz-Source: browser-call-N` maps to their order in the compiled app:
1/2 historical loaders, 3 current daily loader, 4 historical answer retry,
5 next-question handler, 6 current answer/date-error retry. These are diagnostic
client assertions, not authentication or proof that the official browser sent it.
The API still requires authentication and still returns 401 when appropriate.

`jjV203DayCheck` runs every 15 seconds and on focus/visibility change. It retained
an old question after logout and could call the loader without `me`. The compiler
now prevents this callback from requesting while signed out or hidden. This is a
confirmed code path; it does NOT prove the previously observed ~60-second requests
came from this path. Old cached tabs and external clients remain unmarked.

`jj_connection` / `quiz_response` logs status, random request ID, allowlisted caller,
coarse user-agent family, same-site fetch metadata and credential-presence only.
No token, cookie, query, raw UA/referrer/IP or response body is logged.

## WebSocket diagnostics

Ring `/ws/tables/` only. `ws_start`, `ws_accepted`, `ws_first_state`, `ws_end` share
an opaque connection ID. `ws_accepted` means ASGI transport acceptance, not auth
success (the existing route accepts before checking auth). First-state records
confirm a successful ASGI send, not receipt/rendering on the player's device.

End records contain close code, exception type only, duration, last application
text-ping age and last delivered state's phase, action seat/deadline, can_act and
opaque hand reference. Native protocol ping/pong frames are handled by Uvicorn
and are not exposed by ASGI; this patch cannot report their timestamps or assert
that code 1006 was specifically a keepalive timeout.

`table_http` records action POST and state GET response status with the same
opaque table/session references. It records no action payload. This permits
correlation of fallback state retrieval, accepted/rejected actions and reconnect
first-state delivery; it does not itself prove a timeout fold or quantify loss.

References use process-random HMAC keys. Same-cookie/table reconnects within
5 minutes can reference a previously closed connection; cache is capped at 2048.
This is a correlation hint (multiple tabs may share cookies), not unique device
identity. Restart, cookie change or overlapping connections can prevent linking.
No DB queries/writes or additional heartbeats are introduced. Ordinary HTTP state
polling is logged per request; monitor log volume after rollout.

## Historical Ring (Issue #186)

Commit c2d5147 (2026-09-10 JST) introduced a one-time DELETE of
`online_hand_results` only, guarded atomically by migration key
`2026-09-10-clear-existing-online-results`. Commit 010921d merged that behavior.
The current app still calls this guarded migration. This is a candidate explanation
for early missing result rows, not proof that the previously reported 225+2 hands
were deleted by it. Historical analytics was added later; source dates alone do
not establish actual deployment/cleanup times or captured primary evidence.

Run `ops/ring_historical_evidence.sql` through a read-only administrator DB path.
It opens REPEATABLE READ / READ ONLY, sets a 20-second statement timeout, returns
aggregate evidence availability by JST date and cleanup window, then ROLLBACKs.
Do not import the production app as an audit shortcut: startup performs migrations.
The SQL has been schema-reviewed but not executed against production PostgreSQL.

Compare migration timestamp, missing-hand windows, partial_capture and remaining
player outcomes/snapshots. Compare to original deployment logs and verified
backups before attributing a cause. Do not restore results or ranking points from
counts alone. The original 140 pre-fix rake differences require contemporary
policy evaluation; this change does not reprice them.

## Validation

Passed: production-asset build and Node syntax, prebuilt-asset contract,
isolated daily-quiz SQLite integration, WebSocket authentication regression,
ASGI diagnostics/reconnect/redaction/error propagation, and executable signed-out,
hidden, authenticated and busy day-check cases. Full production-safe release gate passed: 7 groups / 49 tests. Production observation remains outstanding.

## Approved production read-only follow-up

On 2026-10-24, sampled application logs again showed quiz 401 requests from the
same source at approximately 60-second intervals (for example 09:50:31, 09:51:31,
09:52:31 UTC). They contain no caller marker or user-agent, so browser versus
external script attribution remains unresolved. No raw IP is included here.

The 2026-10-22 01:19:27 UTC startup audit covered 11,047 hands and 24,497 result
rows: current_anomaly_total=0, points_mismatch=0, legacy completeness/conservation
issues=227 (225 player-count mismatches and two conservation offsets). These are
a startup snapshot, not a current DB recount. Of the 227, 22 and 50 fall in the
two post-uncalled-fix policy windows on September 14. A cleanup nominally named
September 10 therefore cannot explain all rows simply from its name/date: actual
applied_at must be read before attribution.

Four keepalive timeout error entries occurred on October 22 at 00:31:36,
00:33:14, 12:50:14 and 13:24:05 UTC in the queried interval from October 22 onward.
Companion Future-exception lines duplicate these events; they are not extra
independent disconnects. Existing logs cannot establish lost actions or folds.

The Render read-only SQL connector rejected the migration timestamp query because
the DB external IP allowlist is empty. Its hosted connector has no allowlistable
IP. Network policy was not widened and historical SQL remains unexecuted.
