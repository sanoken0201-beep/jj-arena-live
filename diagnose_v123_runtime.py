from __future__ import annotations

import re
import tempfile
from pathlib import Path

from runtime_builder import build_runtime

root = build_runtime(Path(tempfile.mkdtemp(prefix="jj-v123-diag-")) / "runtime")
engine = (root / "poker_engine.py").read_text(encoding="utf-8")
server = (root / "server.py").read_text(encoding="utf-8")
app = (root / "static" / "app.js").read_text(encoding="utf-8")


def excerpts(label: str, text: str, needles: list[str]) -> None:
    print(f"=== {label} ===")
    seen: set[tuple[int, int]] = set()
    for needle in needles:
        for match in list(re.finditer(re.escape(needle), text, re.I))[:6]:
            start = max(0, match.start() - 650)
            end = min(len(text), match.end() + 1400)
            key = (start, end)
            if key in seen:
                continue
            seen.add(key)
            print(f"--- {needle} @{match.start()} ---")
            print(text[start:end])


excerpts("ENGINE", engine, ["rake", "_award_uncontested", "_showdown", "_auto_progress_if_needed", "next_hand_at_epoch"])
excerpts("SERVER", server, ["rake", "auto_deal_loop", "timeout_loop", "ActionIn", "processed_action"])
excerpts("APP", app, ["function cardHTML", "renderActionBar=function", "jjBetPos=function", "jjActionClock", "jjV121ActionPending"])
