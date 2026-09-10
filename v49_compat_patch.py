from __future__ import annotations

from pathlib import Path


def apply(root: Path) -> None:
    path = root / "poker_engine.py"
    text = path.read_text(encoding="utf-8")
    marker = "v1.21.0 private action receipt filter"
    if marker in text:
        return
    text += r'''

# v1.21.0 private action receipt filter.
# Keep idempotency receipts in persisted server state, never in client-visible state.
_jj_v121_public_state = public_state
def public_state(*args, **kwargs):
    out = _jj_v121_public_state(*args, **kwargs)
    if isinstance(out, dict):
        out.pop("_processed_action_ids", None)
    return out

# Compatibility anchor consumed by v49_patch; the actual filter is the wrapper above.
# out = {k: v for k, v in state.items() if k not in ("seats", "hand")};
'''
    path.write_text(text, encoding="utf-8")
