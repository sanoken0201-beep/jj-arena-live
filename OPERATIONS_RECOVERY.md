# JJ Arena operations / recovery

## PostgreSQL backup

The application stores authoritative users, point ledgers, quiz answers, hand analytics and live table state in PostgreSQL. Before a destructive migration or a manual recovery, create a logical dump from an environment that has `DATABASE_URL` available:

```bash
pg_dump --format=custom --no-owner --no-acl "$DATABASE_URL" > jj-arena-$(date +%Y%m%d-%H%M).dump
```

Do not commit dumps or connection strings to GitHub. Keep dumps in access-controlled storage outside the web service.

## PostgreSQL restore

Restore into a new/empty recovery database first. Do not overwrite production before validation.

```bash
pg_restore --clean --if-exists --no-owner --no-acl --dbname "$RECOVERY_DATABASE_URL" jj-arena-YYYYMMDD-HHMM.dump
```

Validate `/api/health`, account counts, `point_ledger`, `quiz_daily_answers`, `jj_hand_history`, and both rows in `tables` before switching a service to the recovered database.

## Live-table recovery

Every successful table-state save is also snapshotted by `resilience.py`. Only changed states are retained and the latest 40 copies per table are kept. A snapshot contains the full private state needed to resume an in-progress hand, including the deck; it is therefore admin/server data and must never be exposed to ordinary users.

Admin endpoints:

- `GET /api/admin/console/resilience` — backup/error health.
- `GET /api/admin/console/table-backups?table_id=<id>` — snapshot metadata only.
- `POST /api/admin/console/table-backups/<backup_id>/restore` with JSON `{ "confirm": "RESTORE" }` — restore one snapshot. The current state is snapshotted before restoration and the operation is written to `admin_audit_log`.

On application startup, invalid/unparseable current table JSON is automatically replaced by the latest valid snapshot when one exists. A normal server restart does not require restoration because `tables.state_json` is already written after each accepted action.

## Sit&Go state recovery

Sit&Go authoritative game state lives in `sitngo_games.state_json` rather than the Ring `tables` row. The runtime therefore maintains its own `sitngo_state_backups` generations. Up to 40 meaningful snapshots are retained per event. The five-second lifecycle heartbeat does not consume generations when only revision/elapsed-clock fields changed.

A normal restart resumes the persisted current state. If the current Sit&Go JSON cannot be parsed or fails the event/revision structure check, the runtime automatically selects the newest valid snapshot for that same event and atomically restores both `state_json` and its matching revision. Recovery is recorded as `sitngo_state_auto_restore` in the operations error log. If no valid same-event snapshot exists, recovery fails closed instead of creating a new tournament state.

Snapshots contain private cards/deck state and are server-only data. They are not exposed through player APIs.

## WebSocket / action recovery

The browser keeps the existing WebSocket reconnect loop and HTTP polling fallback. v1.21 adds a client `action_id`; accepted IDs are stored with the persisted table state. A retry with the same ID returns the current state without applying the poker action twice. Recent IDs are not included in `public_state`.

## Database capacity

The admin operations endpoint reads the current PostgreSQL database size. Set `JJ_DB_CAPACITY_MB` to the storage ceiling for the active Render database plan to enable a percentage and the >=80% warning. If the plan changes, update the environment variable rather than hard-coding a provider limit into the application.

## Incident checklist

1. Stop manual point adjustments while the incident is being checked.
2. Inspect Admin Console > operations for point anomalies and recent errors.
3. Verify `/api/health` and table state before restarting services.
4. If a table state itself is damaged, restore a table snapshot; otherwise let the persisted current state resume normally.
5. For database-level corruption or an incorrect destructive migration, restore a PostgreSQL dump into a recovery database and validate it before cutover.
6. Record any manual recovery in the incident notes; table restores are automatically audit-logged.
