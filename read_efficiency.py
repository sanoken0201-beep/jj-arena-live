"""Result-preserving query reuse outside the immutable materialized core."""
from __future__ import annotations

from contextlib import contextmanager
from types import FunctionType

class _BoundDB:
    """Give unchanged read endpoints one connection, scoped to one request."""
    def __init__(self, db, con):
        self.db, self.con = db, con

    def __getattr__(self, name):
        return getattr(self.db, name)

    @contextmanager
    def connect(self):
        yield self.con


def _on_connection(function, db, con, **kwargs):
    # Clone only the globals mapping; neither module-global db.connect nor the
    # original endpoint is mutated. Concurrent requests cannot share a handle.
    namespace = dict(function.__globals__, db=_BoundDB(db, con))
    bound = FunctionType(function.__code__, namespace, function.__name__,
                         function.__defaults__, function.__closure__)
    bound.__kwdefaults__ = function.__kwdefaults__
    return bound(**kwargs)


class _SettlementConnection:
    """Batch the existing lookup without duplicating any settlement arithmetic."""
    USER_QUERY = "SELECT name,ranking_name FROM users WHERE id=?"

    def __init__(self, con, state):
        self.con = con
        self.state = state
        self.users = None

    def __getattr__(self, name):
        return getattr(self.con, name)

    def execute(self, sql, params=()):
        if sql != self.USER_QUERY:
            return self.con.execute(sql, params)
        if self.users is None:
            ids = sorted({int(net["user_id"]) for net in (self.state.get("last_result") or {}).get("net_results", [])})
            placeholders = ",".join("?" for _ in ids)
            rows = self.con.execute(f"SELECT id,name,ranking_name FROM users WHERE id IN ({placeholders})", ids).fetchall()
            self.users = {int(row["id"]): {"name": row["name"], "ranking_name": row["ranking_name"]} for row in rows}
        row = self.users.get(int(params[0]))

        class Result:
            def fetchone(self):
                return row

        return Result()


def install(app, server, db, *, public_table_limit=None):
    # Keep the browser transform importable in dependency-free asset jobs.
    from fastapi import Depends

    if getattr(app.state, "jj_read_efficiency", False):
        return
    original_record = db._record_online_hand

    def record(con, state):
        return original_record(_SettlementConnection(con, state), state)

    record.__wrapped__ = original_record
    db._record_online_hand = record

    def me(user=Depends(server.current_user)):
        return {key: user[key] for key in ("id", "name", "role", "xp", "disabled", "ranking_name", "created_at")}

    for route in app.router.routes:
        if getattr(route, "path", None) == "/api/me" and "GET" in (getattr(route, "methods", None) or ()):
            route.endpoint = route.dependant.call = me
    server.me = me

    def home_core(user=Depends(server.current_user)):
        with db.connect() as con:
            readers = {
                "rankings": server.rankings,
                "schedules": server.schedules,
                "announcements": server.announcements,
            }
            result = {name: _on_connection(reader, db, con, user=user)
                      for name, reader in readers.items()}
            tables = _on_connection(server.tables, db, con, user=user)
            result["tables"] = tables[:public_table_limit] if public_table_limit is not None else tables
            return result

    def points_dashboard(user=Depends(server.admin_user)):
        # The aggregate exists only for the admin point-entry screen. Individual
        # legacy read endpoints retain their existing compatibility permissions.
        with db.connect() as con:
            return {"entries": _on_connection(server.entries, db, con, limit=40, archive=False, user=user),
                    "ranking_names": _on_connection(server.ranking_names, db, con, user=user)}

    for path, endpoint in (("/api/home/core", home_core), ("/api/points/dashboard", points_dashboard)):
        app.add_api_route(path, endpoint, methods=["GET"])
        # The canonical SPA catch-all must not shadow these read endpoints.
        app.router.routes.insert(0, app.router.routes.pop())
    app.state.jj_read_efficiency = True


CLIENT_HELPER = """
  // Read aggregation only: no response cache, throttling, or update delay.
  async function jjReadBundle(path,keys,legacy){
    try{
      const data=await api(path);
      if(!data||!keys.every(key=>Array.isArray(data[key])))throw new Error('Invalid aggregate response');
      return keys.map(key=>data[key]);
    }catch(error){
      if(!me)throw error;
      return Promise.all(legacy.map(path=>api(path)));
    }
  }
"""


def transform_app_js(js):
    home = "Promise.all([api('/rankings'),api('/schedules'),api('/announcements'),api('/tables')])"
    points = "Promise.all([api('/entries?limit=40'),api('/ranking-names')])"
    if js.count(home) != 1 or js.count(points) != 1 or js.count("  async function renderHome(){") != 1:
        raise RuntimeError("aggregate read sites drifted; review the served client before patching")
    js = js.replace(home, "jjReadBundle('/home/core',['rankings','schedules','announcements','tables'],['/rankings','/schedules','/announcements','/tables'])", 1)
    js = js.replace(points, "jjReadBundle('/points/dashboard',['entries','ranking_names'],['/entries?limit=40','/ranking-names'])", 1)
    return js.replace("  async function renderHome(){", CLIENT_HELPER + "  async function renderHome(){", 1)
