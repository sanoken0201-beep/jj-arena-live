# JJ Arena Feature Lifecycle

This file separates the product that is actively supported from data/backends kept only for compatibility. New work should use the active surface and must not revive a compatibility/retired surface accidentally.

| Surface | State | Contract |
|---|---|---|
| Name + 6-digit PIN login | Active | Canonical authentication flow |
| Home / Ranking / Announcements / Poker Lab | Active | Primary player surfaces |
| Ring game | Active | Exactly one public 6-max ring table |
| Official point entry | Active | Current club point-entry workflow |
| `/admin` management console | Active | Canonical account/point/admin surface |
| Hand analysis/review | Active | Supported post-hand review surface |
| Sit&Go | Active, independent | Separate tournament runtime; not a reason to reuse legacy `PointEntry.game_type=tournament` |
| Schedule backend/data | Compatibility retained | Historical dates stay readable and are appended to Announcements; no primary Schedule navigation |
| Strategy discussion backend/data | Compatibility retained | Keep historical data/routes for rollback/history; no primary navigation |
| Historical second ring table | Compatibility retained | Internal data/rollback only; never exposed as table selection |
| Historical frontend transform modules | Compatibility retained | Build-only implementation detail; `frontend_build_pipeline.py` is the production entrypoint |
| `/api/admin/members*` | Retired | Authenticated 410 tombstone; use `/api/admin/console/users*` |
| Email signup/login | Retired | 410 compatibility response; PIN login only |
| In-hand chat/action-log UI | Retired | Post-hand history/review remains |
| Bet-size preset buttons | Retired | Manual numeric bet/raise input only |
| Separate Schedule/Discussion primary navigation | Retired | Do not restore without an explicit product decision |

The machine-readable equivalent is `feature_lifecycle.py`; regression tests enforce the important routing/UI boundaries.
