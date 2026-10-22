"""Read-only offline snapshot export; never invoked by a web request."""
from datetime import datetime, timedelta, timezone
import argparse
import json
from mda_offline_audit import connect_read_only
from mda_online_population_v2 import audit_online_population

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=24)).isoformat()
    with connect_read_only(args.sqlite) as con:
        if con.postgres:
            con.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            con.execute("SET LOCAL statement_timeout='30000ms'")
        else:
            con.execute("BEGIN")
        report = audit_online_population(con, completed_before=cutoff)
    print(json.dumps({"format_version": "mda-v2-offline-snapshot",
                      "generated_at": now.isoformat(), "data_as_of": cutoff,
                      "report": report}, ensure_ascii=False))

if __name__ == "__main__":
    main()
