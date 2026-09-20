"""Sit&Go alert thresholds, privacy, delivery and retry regression."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.pop("JJ_SITNGO_ALERT_WEBHOOK_URL", None)
_tmp = None
if not os.environ.get("DATABASE_URL"):
    _tmp = tempfile.TemporaryDirectory(prefix="jj-sng-alert-")
    os.environ["JJ_DB_PATH"] = str(Path(_tmp.name) / "alerts.sqlite3")

from fastapi.testclient import TestClient
from smoke_test_sitngo_phase1 import production_app as prod
import sitngo_alerting
import sitngo_observability


class Receiver(BaseHTTPRequestHandler):
    payloads: list[dict] = []
    fail_next = False

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        payload = json.loads(body.decode("utf-8"))
        type(self).payloads.append(payload)
        if type(self).fail_next:
            type(self).fail_next = False
            self.send_response(500)
        else:
            self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        return


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    db = prod.db
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with db.connect() as con:
        con.execute("DELETE FROM sitngo_runtime_metrics")
        con.execute("DELETE FROM sitngo_runtime_alerts")

    threshold = sitngo_alerting.ALERT_THRESHOLDS["stale_turn"]
    for _ in range(threshold - 1):
        require(sitngo_observability.record(db, "stale_turn", now=now), "metric record failed")
    require(not sitngo_alerting.admin_status(db, now=now)["recent"], "alert queued before threshold")

    sitngo_observability.record(db, "stale_turn", now=now)
    status = sitngo_alerting.admin_status(db, now=now)
    require(len(status["recent"]) == 1, "threshold did not queue exactly one alert")
    require(status["recent"][0]["observed_count"] == threshold, "queued alert count mismatch")

    sitngo_observability.record(db, "stale_turn", now=now)
    status = sitngo_alerting.admin_status(db, now=now)
    require(len(status["recent"]) == 1, "same metric/day produced duplicate alerts")
    require(status["recent"][0]["observed_count"] == threshold + 1, "alert count did not update")

    for _ in range(30):
        sitngo_observability.record(db, "timeout_auto_action", now=now)
    status = sitngo_alerting.admin_status(db, now=now)
    require(
        all(x["metric"] != "timeout_auto_action" for x in status["recent"]),
        "normal unattended timeout must not page administrators",
    )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    os.environ["JJ_SITNGO_ALERT_WEBHOOK_URL"] = f"http://127.0.0.1:{server.server_port}/alerts"
    try:
        result = sitngo_alerting.dispatch_pending(db, now=now)
        require(result["sent"] == 1 and result["failed"] == 0, f"webhook delivery failed: {result}")
        require(len(Receiver.payloads) == 1, "webhook received wrong number of payloads")
        payload = Receiver.payloads[0]
        require(payload["metric"] == "stale_turn" and payload["observed_count"] == threshold + 1, "wrong alert payload")
        require(payload["alert_key"] == f"{now.date().isoformat()}:stale_turn:{threshold}", "alert dedupe key mismatch")
        require(
            set(payload) == {"type","source","alert_key","severity","metric","day","observed_count","threshold","text"},
            f"alert payload grew an unreviewed field: {payload}",
        )
        forbidden = ("user_id","event_id","table_id","hand_id","cards","chip_amount","session_id","ip_address","webhook_url")
        serialized = json.dumps(payload, sort_keys=True).lower()
        require(all(word not in serialized for word in forbidden), f"alert payload leaked identifier category: {payload}")

        sitngo_observability.record(db, "restart_recovery", now=now)
        Receiver.fail_next = True
        failed = sitngo_alerting.dispatch_pending(db, now=now)
        require(failed["failed"] == 1 and failed["sent"] == 0, "webhook failure was not retained")
        status = sitngo_alerting.admin_status(db, now=now)
        recovery = next(x for x in status["recent"] if x["metric"] == "restart_recovery")
        require(recovery["status"] == "pending" and recovery["attempts"] == 1, "failed alert was not left retryable")
        require(recovery["last_error_code"] == "http_500", "failure stored unsafe/unexpected detail")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    os.environ.pop("JJ_SITNGO_ALERT_WEBHOOK_URL", None)
    with db.connect() as con:
        admin = int(con.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()["id"])
    client = TestClient(prod.app, base_url="https://testserver")
    token = prod.db.create_session(admin)
    client.headers["Authorization"] = "Bearer " + token
    response = client.get("/api/admin/sitngo/alerts?days=7")
    require(response.status_code == 200, response.text)
    data = response.json()
    require(data["webhook_configured"] is False and data["pending_count"] >= 1, "admin alert status mismatch")
    require(data["privacy"]["exposes_webhook_url"] is False, "privacy contract missing")
    require("127.0.0.1" not in response.text and "JJ_SITNGO_ALERT_WEBHOOK_URL" not in response.text, "webhook secret/address exposed")
    client.close()

    print("JJ_SITNGO_ALERTING_OK")


if __name__ == "__main__":
    main()
