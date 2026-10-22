"""Offline export -> delayed admin API, authorization and invalid snapshot checks."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mda_admin_api import install
from mda_online_population_v2 import audit_online_population
from smoke_test_mda_admin_cache import _server
from smoke_test_mda_all_players import _db, _seed

class NoDatabase:
    def connect(self):
        raise AssertionError("web request accessed database")

def run():
    con = _db()
    for i in range(120):
        _seed(con, i, 6)
    # Ensure both the cutoff and the paginated path exclude newer hands.
    con.execute("UPDATE jj_hand_history SET completed_at='2099-01-01T00:00:00+00:00' WHERE hand_id LIKE '%00119%'")
    con.execute("CREATE TABLE jj_hand_action_eligibility(hand_id TEXT, seq INTEGER, can_increase_wager INTEGER)")
    con.execute("INSERT INTO jj_hand_action_eligibility SELECT hand_id,seq,1 FROM jj_hand_actions")
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=25)).isoformat()
    report = audit_online_population(con, completed_before=cutoff, batch_size=19)
    assert report["coverage"]["hands_examined"] == 119
    doc = {"format_version":"mda-v2-offline-snapshot",
           "generated_at":now.isoformat(), "data_as_of":cutoff, "report":report}
    app = FastAPI()
    install(app, _server(), NoDatabase())
    client = TestClient(app)
    url = "/api/admin/mda/population"
    headers = {"x-test-role":"admin"}
    with TemporaryDirectory() as directory:
        path = Path(directory) / "snapshot.json"
        with patch.dict(os.environ, {"JJ_MDA_V2_SNAPSHOT_PATH":str(path)}):
            assert client.get(url).status_code == 401
            assert client.get(url, headers={"x-test-role":"member"}).status_code == 403
            assert client.get(url, headers=headers).json()["status"] == "not_ready"
            path.write_text(json.dumps(doc))
            result = client.get(url, headers=headers)
            assert result.status_code == 200, result.text
            assert result.headers["cache-control"] == "private, no-store"
            assert result.json()["cohorts_by_players_dealt_in"]["6"]["metrics"]["rfi"]["status"] == "observed"
            assert "user_id" not in result.text and "hand_id" not in result.text
            for change in ("partial", "recent", "expired", "wrong_cutoff", "old_policy", "invalid", "oversized"):
                bad = deepcopy(doc)
                if change == "partial": bad["report"]["coverage"]["complete_scan"] = False
                if change == "recent": bad["data_as_of"] = now.isoformat()
                if change == "expired": bad["generated_at"] = (now - timedelta(days=8)).isoformat()
                if change == "old_policy": bad["report"].pop("eligibility_policy")
                if change == "wrong_cutoff": bad["report"]["coverage"]["completed_before"] = None
                path.write_text("null" if change == "invalid" else " " * 2_000_001 if change == "oversized" else json.dumps(bad))
                assert client.get(url, headers=headers).status_code == 503, change
    con.close()
    print("smoke_test_mda_population_api_v2: PASS")

if __name__ == "__main__":
    run()
