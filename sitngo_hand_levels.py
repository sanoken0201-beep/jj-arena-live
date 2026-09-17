"""Hand-count blind progression for JJ Arena Sit&Go tournaments.

New tournaments advance one blind level after every 12 completed hands.  The
change is intentionally isolated from the immutable ring-game core and from
already-running legacy tournaments: only states created with ``level_mode`` set
to ``hands`` use this scheduler.

The persisted minute fields remain as schema/rollback compatibility metadata;
they are not consulted for blind progression in hand-count tournaments.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HANDS_PER_LEVEL = 12
LEVEL_MODE = "hands"
PLAYER_UI_MARKER = "jj sng 12-hand levels 2026-09-18"
ADMIN_UI_MARKER = "jj sng admin 12-hand levels 2026-09-18"
ADMIN_CACHE_QUERY = "hl=12hands-20260918-1"


def level_index_for_completed_hands(completed_hands: int, level_count: int) -> int:
    """Return the zero-based level used by the *next* hand."""
    count = max(1, int(level_count))
    completed = max(0, int(completed_hands))
    return min(completed // HANDS_PER_LEVEL, count - 1)


def _replace_prefixed_line(source: str, prefix: str, replacement: str, *, required: bool = True) -> str:
    lines = source.splitlines(keepends=True)
    matches = [i for i, line in enumerate(lines) if line.startswith(prefix)]
    if not matches:
        if required:
            raise RuntimeError(f"Sit&Go 12-hand UI drift: missing {prefix!r}")
        return source
    if len(matches) != 1:
        raise RuntimeError(f"Sit&Go 12-hand UI drift: duplicate {prefix!r}")
    newline = "\n" if lines[matches[0]].endswith("\n") else ""
    lines[matches[0]] = replacement.rstrip("\n") + newline
    return "".join(lines)


def _patch_player_ui() -> None:
    import sitngo_ui as ui

    if getattr(ui, "_JJ_HAND_LEVELS_PATCHED", False):
        return

    ui._SITNGO_PANEL = ui._SITNGO_PANEL.replace(
        "6-MAX · ADMIN STRUCTURE · BB ANTE",
        "6-MAX · 12 HAND LEVELS · BB ANTE",
    ).replace(
        "6-MAX · 10 MIN LEVELS · BB ANTE",
        "6-MAX · 12 HAND LEVELS · BB ANTE",
    )

    source = ui._APP_PATCH
    if "  const jjSngLevelSummary=" in source:
        source = _replace_prefixed_line(
            source,
            "  const jjSngLevelSummary=",
            "  const jjSngLevelSummary=levels=>'12ハンド/レベル';",
        )
    source = _replace_prefixed_line(
        source,
        "  function jjSngStructureHtml(",
        "  function jjSngStructureHtml(levels){return `<details class=\"jj-sng-structure\"><summary>ブラインドストラクチャーを見る</summary><div class=\"jj-sng-levels\">${(levels||[]).map(x=>`<div class=\"jj-sng-level\"><span>Lv.${x.level}</span><b>${fmt(x.small_blind)} / ${fmt(x.big_blind)}</b><small>BBA ${fmt(x.bb_ante)} · 12ハンド</small></div>`).join('')}</div></details>`}",
    )
    source = source.replace(
        "jjSngStructureHtml(eventLevels,event.target_minutes)",
        "jjSngStructureHtml(eventLevels)",
    )
    source = source.replace("10分レベル", "12ハンド/レベル")

    old_clock = "    el.innerHTML=`<span>Lv.${Number(t.level)} · ${fmt(tableState.small_blind)}/${fmt(tableState.big_blind)} · BBA ${fmt(t.bb_ante)}</span><span>残り${Number(t.remaining)}/${Number(t.entrants)}人${t.status==='finished'?' · 終了':t.next_level_at?` · 次 ${jjSngCountdown(t.next_level_at)}`:''}</span>`;"
    new_clock = "    el.innerHTML=`<span>Lv.${Number(t.level)} · ${fmt(tableState.small_blind)}/${fmt(tableState.big_blind)} · BBA ${fmt(t.bb_ante)}</span><span>${t.status==='finished'?'終了':`${Number(t.hand_in_level||0)}/${Number(t.hands_per_level||12)}ハンド`} · 残り${Number(t.remaining)}/${Number(t.entrants)}人</span>`;"
    if old_clock not in source:
        raise RuntimeError("Sit&Go 12-hand UI drift: table clock contract changed")
    source = source.replace(old_clock, new_clock, 1)
    source += f"\n  // {PLAYER_UI_MARKER}\n"
    ui._APP_PATCH = source
    ui._JJ_HAND_LEVELS_PATCHED = True


def transform_admin_js(source: str) -> str:
    """Keep legacy minute payloads hidden while making the admin contract clear."""
    if ADMIN_UI_MARKER in source:
        return source

    output = source.replace(
        "SB / BB / BBA / 各レベル時間を大会ごとに設定",
        "SB / BB / BBAを大会ごとに設定 · ブラインドは12ハンドごとに上昇",
    )
    output = output.replace(
        '<span>分</span><span></span>',
        '<span>進行</span><span></span>',
    )
    minute_input = '<label><span>分</span><input type="number" min="1" max="60" step="1" value="${x.minutes}" data-sng-field="minutes" required></label>'
    fixed_input = '<label><span>進行</span><input type="text" value="12ハンド" disabled aria-label="12ハンド固定"></label><input type="hidden" value="10" data-sng-field="minutes">'
    if minute_input not in output:
        raise RuntimeError("Sit&Go 12-hand admin UI drift: minute editor not found")
    output = output.replace(minute_input, fixed_input, 1)

    output = _replace_prefixed_line(
        output,
        "  function renderStructure(",
        "  function renderStructure(levels,targetMinutes){return `<details class=\"sng-structure-admin\"><summary>ブラインドストラクチャー</summary><div class=\"sng-structure-grid\">${(levels||[]).map(x=>`<div><b>Lv.${x.level} · ${fmt(x.small_blind)}/${fmt(x.big_blind)}</b><small>BBA ${fmt(x.bb_ante)} · 12ハンド</small></div>`).join('')}</div></details>`}",
    )
    output = output.replace(
        '<span>準備 ${fmt(e.prepared_minutes)}分</span>',
        '<span>進行 12ハンド/Lv</span>',
    )
    output = output.replace(
        '<div><span>標準目標</span><b>${d.target_minutes}分</b></div>',
        '<div><span>ブラインド上昇</span><b>12ハンドごと</b></div>',
    )
    output = output.replace(
        "最終レベル到達後は、そのレベルを大会終了まで継続します。チップ値は100点単位です。",
        "各レベル12ハンド固定です。最終レベル到達後は、そのレベルを大会終了まで継続します。チップ値は100点単位です。",
    )
    return output + f"\n// {ADMIN_UI_MARKER}\n"


def transform_admin_index(source: str) -> str:
    if ADMIN_CACHE_QUERY in source:
        return source
    needle = '<script src="/admin-static/admin_sitngo.js"></script>'
    if source.count(needle) != 1:
        raise RuntimeError("Sit&Go 12-hand admin cache drift: script tag not found exactly once")
    return source.replace(
        needle,
        f'<script src="/admin-static/admin_sitngo.js?{ADMIN_CACHE_QUERY}"></script>',
        1,
    )


def _patch_admin_assets() -> None:
    root = Path(__file__).resolve().parent / "admin_static"
    js_path = root / "admin_sitngo.js"
    index_path = root / "index.html"
    js_path.write_text(transform_admin_js(js_path.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
    index_path.write_text(transform_admin_index(index_path.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")


def _patch_service_contract(sitngo_module) -> None:
    service_cls = sitngo_module.SitNGoService
    if getattr(service_cls, "_jj_hand_levels_contract", False):
        return

    original_payload = service_cls._event_payload
    original_admin_events = service_cls.admin_events

    def event_payload(self, row, user_id=None, *, admin=False):
        payload = original_payload(self, row, user_id, admin=admin)
        tournament = payload.get("tournament") or {}
        if str(payload.get("status")) in {"running", "finished"} and tournament:
            mode = str(tournament.get("level_mode") or "time")
            payload["level_mode"] = mode
            payload["hands_per_level"] = int(tournament.get("hands_per_level") or HANDS_PER_LEVEL) if mode == LEVEL_MODE else None
        else:
            payload["level_mode"] = LEVEL_MODE
            payload["hands_per_level"] = HANDS_PER_LEVEL
        return payload

    def admin_events(self, actor_id: int):
        result = original_admin_events(self, actor_id)
        defaults = result.setdefault("defaults", {})
        defaults["level_mode"] = LEVEL_MODE
        defaults["hands_per_level"] = HANDS_PER_LEVEL
        return result

    service_cls._event_payload = event_payload
    service_cls.admin_events = admin_events
    service_cls._jj_hand_levels_contract = True


def _patch_runtime(runtime_module) -> None:
    runtime_cls = runtime_module.TournamentRuntime
    if getattr(runtime_cls, "_jj_hand_levels_installed", False):
        return

    original_create = runtime_cls.create
    original_tick = runtime_cls.tick
    original_public = runtime_cls.public

    def create(self, con, event, participants, now):
        original_create(self, con, event, participants, now)
        row = con.execute(
            "SELECT state_json,revision FROM sitngo_games WHERE event_id=?",
            (event["id"],),
        ).fetchone()
        if not row:
            return
        state = json.loads(row["state_json"])
        tournament = state.get("tournament") or {}
        if tournament.get("level_mode") == LEVEL_MODE:
            return
        tournament.update(
            level_mode=LEVEL_MODE,
            hands_per_level=HANDS_PER_LEVEL,
            level_started_hand_no=1,
        )
        state["tournament"] = tournament
        updated = con.execute(
            "UPDATE sitngo_games SET state_json=?,updated_at=? WHERE event_id=? AND revision=?",
            (json.dumps(state, ensure_ascii=False), self.db.utcnow(), event["id"], row["revision"]),
        )
        if updated.rowcount != 1:
            raise RuntimeError("Sit&Go hand-level initialization lost update")

    async def tick(self, eid, *, now=None, recover=False):
        probe = self.load(eid)
        if (probe.get("tournament") or {}).get("level_mode") != LEVEL_MODE:
            return await original_tick(self, eid, now=now, recover=recover)

        server = self.server
        now = time.time() if now is None else float(now)
        async with server.get_table_lock(eid):
            state = self.load(eid)
            tournament = state["tournament"]
            if tournament["status"] != "running":
                return None

            previous = float(tournament.get("clock_at_epoch") or now)
            if recover:
                delta = max(0.0, now - previous)
                hand = state.get("hand") or {}
                if hand.get("action_deadline"):
                    deadline = datetime.fromisoformat(hand["action_deadline"]).timestamp() + delta
                    hand["action_deadline"] = datetime.fromtimestamp(deadline, timezone.utc).isoformat()
                for obj, key in (
                    (hand, "runout_due_at_epoch"),
                    (state, "next_hand_at_epoch"),
                    (state, "showdown_hold_until_epoch"),
                ):
                    if obj.get(key):
                        obj[key] += delta
            else:
                # Duration remains useful telemetry, but it never selects blinds.
                tournament["elapsed_seconds"] = float(tournament.get("elapsed_seconds") or 0) + max(0.0, now - previous)
            tournament["clock_at_epoch"] = now

            hand = state.get("hand") or {}
            if not recover and state["status"] == "playing":
                if hand.get("forced_runout") and float(hand.get("runout_due_at_epoch") or 0) <= now:
                    self.engine.advance_forced_runout(state)
                elif hand.get("action_deadline") and datetime.fromisoformat(hand["action_deadline"]).timestamp() <= now:
                    player = next((p for p in state["seats"] if p["seat"] == hand.get("action_seat")), None)
                    if player:
                        legal = self.engine.legal_actions(state, player["user_id"])
                        self.engine.apply_action(
                            state,
                            player["user_id"],
                            "check" if legal.get("can_check") else "fold",
                        )
                        server.arm_action_deadline(state)
            elif not recover and state["status"] == "waiting" and float(state.get("next_hand_at_epoch") or 0) <= now:
                levels = list(tournament.get("structure") or [])
                if not levels:
                    raise RuntimeError("Sit&Go blind structure is empty")
                completed_hands = max(0, int(state.get("hand_no") or 0))
                index = level_index_for_completed_hands(completed_hands, len(levels))
                level = levels[index]
                tournament.update(
                    level=index + 1,
                    bb_ante=int(level["bb_ante"]),
                    level_started_hand_no=index * HANDS_PER_LEVEL + 1,
                    hands_per_level=HANDS_PER_LEVEL,
                    level_mode=LEVEL_MODE,
                )
                state.update(
                    small_blind=int(level["small_blind"]),
                    big_blind=int(level["big_blind"]),
                )
                self.engine.start_hand(state)
                server.arm_action_deadline(state)

            self.save(state, notify=False)
            hand = state.get("hand") or {}
            deadlines = [now + 5]
            if state["status"] == "playing":
                if hand.get("action_deadline"):
                    deadlines.append(datetime.fromisoformat(hand["action_deadline"]).timestamp())
                if hand.get("runout_due_at_epoch"):
                    deadlines.append(float(hand["runout_due_at_epoch"]))
            elif tournament["status"] == "running":
                deadlines.append(float(state.get("next_hand_at_epoch") or now + 1.6))
        await server.hub.broadcast(eid)
        return min(deadlines)

    def public(self, state, viewer=None):
        value = original_public(self, state, viewer)
        tournament = value.get("tournament") or {}
        if tournament.get("level_mode") != LEVEL_MODE:
            return value

        level_no = max(1, int(tournament.get("level") or 1))
        hand_no = max(0, int(state.get("hand_no") or 0))
        first_hand = (level_no - 1) * HANDS_PER_LEVEL + 1
        hand_in_level = max(0, min(HANDS_PER_LEVEL, hand_no - first_hand + 1))
        final_level = level_no >= len(tournament.get("structure") or [])
        tournament.update(
            next_level_at=None,
            level_mode=LEVEL_MODE,
            hands_per_level=HANDS_PER_LEVEL,
            hand_in_level=hand_in_level,
            hands_until_level_up=None if final_level else max(0, HANDS_PER_LEVEL - hand_in_level),
            next_level_hand_no=None if final_level else level_no * HANDS_PER_LEVEL + 1,
        )
        value["tournament"] = tournament
        return value

    runtime_cls.create = create
    runtime_cls.tick = tick
    runtime_cls.public = public
    runtime_cls._jj_hand_levels_installed = True


def install(sitngo_module, runtime_module) -> None:
    """Install the fixed 12-hand contract before TournamentRuntime is created."""
    _patch_service_contract(sitngo_module)
    _patch_runtime(runtime_module)
    _patch_player_ui()
    _patch_admin_assets()


__all__ = [
    "ADMIN_CACHE_QUERY",
    "HANDS_PER_LEVEL",
    "LEVEL_MODE",
    "install",
    "level_index_for_completed_hands",
    "transform_admin_index",
    "transform_admin_js",
]
