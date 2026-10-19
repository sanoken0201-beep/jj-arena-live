"""Read a bounded offline export, revalidate and project anonymous v2 cells."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
from mda_online_review_v2 import prepare_review

MAX_SNAPSHOT_BYTES = 2_000_000

def read_snapshot(path: str, now=None) -> dict:
    now = now or datetime.now(timezone.utc)
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_SNAPSHOT_BYTES + 1)
    if len(raw) > MAX_SNAPSHOT_BYTES:
        raise ValueError("oversized snapshot")
    doc = json.loads(raw)
    if doc.get("format_version") != "mda-v2-offline-snapshot":
        raise ValueError("wrong snapshot format")
    generated = datetime.fromisoformat(doc["generated_at"])
    cutoff = datetime.fromisoformat(doc["data_as_of"])
    if generated.tzinfo is None or cutoff.tzinfo is None:
        raise ValueError("timezone required")
    if not now - timedelta(days=7) <= generated <= now:
        raise ValueError("stale or future snapshot")
    if cutoff > generated - timedelta(hours=24):
        raise ValueError("snapshot is not delayed")
    coverage = doc["report"]["coverage"]
    if coverage.get("completed_before") != doc["data_as_of"]:
        raise ValueError("cutoff mismatch")
    review = prepare_review(doc["report"])
    review["generated_at"] = doc["generated_at"]
    review["data_as_of"] = doc["data_as_of"]
    return review
