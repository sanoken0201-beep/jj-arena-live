from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Depends, Query

JST = ZoneInfo("Asia/Tokyo")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except Exception:
        return None


def _table_exists(db, name: str) -> bool:
    with db.connect() as con:
        if getattr(db, "IS_POSTGRES", False):
            r = con.execute("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=?", (name,)).fetchone()
        else:
            r = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return bool(r)


def _columns(db, name: str) -> set[str]:
    with db.connect() as con:
        if getattr(db, "IS_POSTGRES", False):
            rows = con.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=?", (name,)).fetchall()
            return {str(r["column_name"]) for r in rows}
        return {str(r["name"]) for r in con.execute(f"PRAGMA table_info({name})").fetchall()}


def _confidence(n: int) -> str:
    return "high" if n >= 50 else "medium" if n >= 20 else "low"


def learning_payload(hand_analytics, uid: int, range_name: str) -> dict[str, Any]:
    rows = hand_analytics._completed_player_rows(uid, range_name)
    overall = hand_analytics._aggregate(rows)
    positions = hand_analytics._group_dimension(rows, lambda r: r.get("position") or "—")
    pos = {str(x["key"]): x for x in positions}
    out: list[dict[str, Any]] = []

    def add(code, title, fact, candidate, metric, n, study, severity="watch"):
        out.append({"code": code, "severity": severity, "title": title, "fact": fact,
                    "candidate": candidate, "metric": metric, "sample_size": int(n),
                    "confidence": _confidence(int(n)), "study_target": study, "solver_judgement": False})

    btn, co = pos.get("BTN") or pos.get("BTN/SB"), pos.get("CO")
    if btn and co and int(btn["hands"]) >= 20 and int(co["hands"]) >= 20:
        b, c = btn["vpip"]["value"], co["vpip"]["value"]
        if b is not None and c is not None and b + 6 <= c:
            add("btn_vpip_below_co", "BTNのVPIPがCOより低い",
                f"{btn['key']} VPIP {b}%（{btn['hands']} hands） / CO {c}%（{co['hands']} hands）。",
                "後ろのポジションで参加レンジが十分に広がっているか確認する候補です。",
                "Position VPIP", min(int(btn["hands"]), int(co["hands"])), "BTN / COのプリフロップ参加レンジ")

    fbs = overall["fold_bb_to_steal"]
    if fbs["n"] >= 15 and fbs["value"] is not None and fbs["value"] >= 75:
        add("bb_vs_steal_fold_high", "BB vs Stealでfoldが多い",
            f"Stealに直面したBB {fbs['n']}回のうち {fbs['value']}% でfoldしています。",
            "BB defenseが狭すぎないか確認する候補です。75%は検出用閾値でGTOの正解値ではありません。",
            "Fold BB to Steal", fbs["n"], "BB vs CO/BTN Steal")

    f3 = overall["fold_to_three_bet"]
    if f3["n"] >= 15 and f3["value"] is not None and f3["value"] >= 75:
        add("fold_to_3bet_high", "3betに対するfoldが多い",
            f"Open後に3betを受けた {f3['n']}回のうち {f3['value']}% でfoldしています。",
            "Open/Foldへ寄りすぎていないかPosition別に確認する候補です。",
            "Fold to 3bet", f3["n"], "3betへのCall / 4bet判断")

    vpip, pfr = overall["vpip"]["value"], overall["pfr"]["value"]
    if len(rows) >= 80 and vpip is not None and pfr is not None and vpip - pfr >= 12:
        add("vpip_pfr_gap", "VPIPとPFRの差が大きい",
            f"{len(rows)} handsで VPIP {vpip}% / PFR {pfr}%、差は {round(vpip-pfr, 1)}ptです。",
            "プリフロップでCallへ寄る局面が多すぎないか確認する候補です。",
            "VPIP-PFR gap", len(rows), "Cold Call / Open Raiseの使い分け")

    three = overall["three_bet"]
    if three["n"] >= 30 and three["value"] is not None and three["value"] <= 4:
        add("three_bet_low", "3bet頻度が低い",
            f"3bet機会 {three['n']}回で実行は {three['value']}% です。",
            "3bet候補をCall/Foldへ寄せていないか確認する候補です。",
            "3bet", three["n"], "Position別3bet候補")

    try:
        with hand_analytics._DB.connect() as con:
            ar = con.execute("""SELECT a.action,a.is_aggressive FROM jj_hand_actions a
                WHERE a.user_id=? AND a.street<>'preflop' AND a.hand_id IN (
                  SELECT hand_id FROM jj_hand_actions WHERE street='preflop' AND is_aggressive=1
                  GROUP BY hand_id HAVING COUNT(*)>=2)""", (uid,)).fetchall()
        actions = [dict(r) for r in ar if str(r["action"]) in {"check", "call", "raise", "allin_raise", "allin_call"}]
        n, ag = len(actions), sum(int(r["is_aggressive"] or 0) for r in actions)
        freq = round(ag * 100 / n, 1) if n else None
        if n >= 20 and freq is not None and freq <= 25:
            add("three_bet_pot_passive", "3bet potでpassiveな傾向",
                f"3bet以上で始まったpotのpostflop {n} actions中、bet/raise系は {ag}回（{freq}%）です。",
                "3bet potでCheck/Callへ寄りすぎていないか実ハンドを確認する候補です。",
                "3bet-pot aggression", n, "3bet potのCbet / Barrel / Check range")
    except Exception:
        pass

    out.sort(key=lambda x: ({"watch": 0, "info": 1}.get(x["severity"], 9), {"high": 0, "medium": 1, "low": 2}[x["confidence"]], -x["sample_size"]))
    recommended = out[0] if out else {"code": "sample_building", "severity": "ok", "title": "大きな頻度偏りはまだ検出されていません",
        "fact": f"対象期間の完全記録は {len(rows)} handsです。", "candidate": "GTO判定ではありません。サンプルを増やしながら差を追跡します。",
        "metric": "Sample", "sample_size": len(rows), "confidence": "high" if len(rows) >= 150 else "medium" if len(rows) >= 50 else "low",
        "study_target": "ハンドレビューを継続", "solver_judgement": False}
    return {"range": range_name, "hands": len(rows), "signals": out[:8], "recommended": recommended,
            "policy": {"solver_used": False, "note": "表示値はJJ Arena内の観測事実です。閾値は検出用であり均衡戦略の正解値ではありません。"}}


def _quiz_anomalies(db) -> list[dict[str, Any]]:
    if not _table_exists(db, "point_ledger"):
        return []
    since = (_now() - timedelta(days=8)).isoformat()
    with db.connect() as con:
        rows = [dict(r) for r in con.execute("""SELECT l.*,u.name user_name FROM point_ledger l JOIN users u ON u.id=l.user_id
            WHERE l.kind='quiz_reward' AND l.created_at>=? ORDER BY l.created_at""", (since,)).fetchall()]
    issues, per_day, per_reason, per_user = [], defaultdict(list), defaultdict(list), defaultdict(list)

    def add(code, row, detail, severity="warning"):
        issues.append({"code": code, "severity": severity, "user_id": int(row.get("user_id") or 0),
                       "user_name": str(row.get("user_name") or "—"), "detail": detail,
                       "detected_at": str(row.get("created_at") or _now().isoformat())})

    for r in rows:
        amount = float(r.get("amount") or 0)
        if amount != 10:
            add("quiz_reward_amount", r, f"quiz_reward が {amount:g}pt です（通常10pt）。", "critical")
        dt = _parse(r.get("effective_at")) or _parse(r.get("created_at"))
        if dt:
            per_day[(int(r["user_id"]), dt.astimezone(JST).date().isoformat())].append(r)
        per_reason[(int(r["user_id"]), str(r.get("reason") or ""))].append(r)
        per_user[int(r["user_id"])].append(r)
    for (_uid, day), group in per_day.items():
        total = sum(max(0, float(r.get("amount") or 0)) for r in group)
        if total > 100:
            add("quiz_daily_limit", group[-1], f"{day} のquiz_reward合計が {total:g}pt で100ptを超えています。", "critical")
    for (_uid, reason), group in per_reason.items():
        if reason and len(group) > 1:
            add("quiz_duplicate_source", group[-1], f"同じ理由のquiz_rewardが {len(group)}件あります。")
    for _uid, group in per_user.items():
        timed = [(r, _parse(r.get("created_at"))) for r in group]
        timed = [(r, d) for r, d in timed if d]
        for i, (_row, start) in enumerate(timed):
            burst = [x for x in timed[i:] if (x[1] - start).total_seconds() <= 30]
            if len(burst) >= 6:
                add("quiz_reward_burst", burst[-1][0], f"30秒以内に {len(burst)}件のquiz_rewardがあります。")
                break
    return issues[:80]


def _db_health(db) -> dict[str, Any]:
    size = None
    try:
        if getattr(db, "IS_POSTGRES", False):
            with db.connect() as con:
                size = int(con.execute("SELECT pg_database_size(current_database()) bytes").fetchone()["bytes"] or 0)
        elif db.DB_PATH.exists():
            size = int(db.DB_PATH.stat().st_size)
    except Exception:
        pass
    cap_mb = float(os.getenv("JJ_DB_CAPACITY_MB", "0") or 0)
    cap = int(cap_mb * 1024 * 1024) if cap_mb > 0 else None
    usage = round(size * 100 / cap, 1) if size is not None and cap else None
    return {"engine": "postgresql" if getattr(db, "IS_POSTGRES", False) else "sqlite", "size_bytes": size,
            "capacity_bytes": cap, "usage_percent": usage, "warning": bool(usage is not None and usage >= 80)}


def operations_payload(db) -> dict[str, Any]:
    now, seven = _now(), (_now() - timedelta(days=7)).isoformat()
    day = now.astimezone(JST).date(); ds = datetime.combine(day, time(), JST).astimezone(timezone.utc); de = ds + timedelta(days=1)
    deleted_expr = "deleted_at IS NOT NULL" if "deleted_at" in _columns(db, "users") else "0=1"
    with db.connect() as con:
        acc = con.execute(f"""SELECT COUNT(*) total,
            SUM(CASE WHEN COALESCE(disabled,0)=0 AND NOT ({deleted_expr}) THEN 1 ELSE 0 END) enabled,
            SUM(CASE WHEN COALESCE(disabled,0)<>0 AND NOT ({deleted_expr}) THEN 1 ELSE 0 END) disabled,
            SUM(CASE WHEN {deleted_expr} THEN 1 ELSE 0 END) deleted FROM users""").fetchone()
        active_ids = {int(r["user_id"]) for r in con.execute("SELECT DISTINCT user_id FROM sessions WHERE created_at>=?", (seven,)).fetchall()}
        ledger = con.execute("""SELECT COUNT(*) transactions,COALESCE(SUM(amount),0) net,
            COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) positive,
            COALESCE(SUM(CASE WHEN amount<0 THEN -amount ELSE 0 END),0) negative,
            COALESCE(SUM(CASE WHEN kind='quiz_reward' THEN amount ELSE 0 END),0) quiz_points
            FROM point_ledger WHERE created_at>=?""", (seven,)).fetchone()
        tables = con.execute("SELECT id,name,state_json,updated_at FROM tables ORDER BY id").fetchall()
    quiz_today = quiz_7d = quiz_users_today = 0
    if _table_exists(db, "quiz_daily_answers"):
        with db.connect() as con:
            qt = con.execute("SELECT COUNT(*) answers,COUNT(DISTINCT user_id) users FROM quiz_daily_answers WHERE answered_at>=? AND answered_at<? AND answer IS NOT NULL", (ds.isoformat(), de.isoformat())).fetchone()
            q7 = con.execute("SELECT COUNT(*) answers FROM quiz_daily_answers WHERE answered_at>=? AND answer IS NOT NULL", (seven,)).fetchone()
            active_ids.update(int(r["user_id"]) for r in con.execute("SELECT DISTINCT user_id FROM quiz_daily_answers WHERE answered_at>=?", (seven,)).fetchall())
        quiz_today, quiz_users_today, quiz_7d = int(qt["answers"] or 0), int(qt["users"] or 0), int(q7["answers"] or 0)
    online_hands = online_users = 0
    if _table_exists(db, "jj_hand_history") and _table_exists(db, "jj_hand_players"):
        with db.connect() as con:
            hh = con.execute("""SELECT COUNT(DISTINCT h.hand_id) hands,COUNT(DISTINCT p.user_id) users FROM jj_hand_history h
                JOIN jj_hand_players p ON p.hand_id=h.hand_id WHERE h.completed_at>=?""", (seven,)).fetchone()
            active_ids.update(int(r["user_id"]) for r in con.execute("""SELECT DISTINCT p.user_id FROM jj_hand_players p JOIN jj_hand_history h ON h.hand_id=p.hand_id WHERE h.completed_at>=?""", (seven,)).fetchall())
        online_hands, online_users = int(hh["hands"] or 0), int(hh["users"] or 0)
    seated, table_status = set(), []
    for r in tables:
        try:
            state = json.loads(r["state_json"]); ids = {int(p["user_id"]) for p in state.get("seats", []) if p.get("user_id")}; seated.update(ids)
            table_status.append({"id": r["id"], "name": r["name"], "status": state.get("status"), "seated": len(ids), "updated_at": r["updated_at"]})
        except Exception:
            table_status.append({"id": r["id"], "name": r["name"], "status": "invalid_state", "seated": 0, "updated_at": r["updated_at"]})
    enabled = int(acc["enabled"] or 0)
    return {"generated_at": now.isoformat(),
        "accounts": {"total": int(acc["total"] or 0), "enabled": enabled, "disabled": int(acc["disabled"] or 0), "deleted": int(acc["deleted"] or 0)},
        "activity": {"active_7d": len(active_ids), "active_rate_7d": round(len(active_ids)*100/enabled, 1) if enabled else 0},
        "quiz": {"answers_today": quiz_today, "users_today": quiz_users_today, "answers_7d": quiz_7d},
        "points": {"transactions_7d": int(ledger["transactions"] or 0), "net_7d": round(float(ledger["net"] or 0),2), "positive_7d": round(float(ledger["positive"] or 0),2), "negative_7d": round(float(ledger["negative"] or 0),2), "quiz_points_7d": round(float(ledger["quiz_points"] or 0),2)},
        "online": {"hands_7d": online_hands, "users_7d": online_users, "seated_now": len(seated), "tables": table_status},
        "anomalies": _quiz_anomalies(db), "database": _db_health(db)}


def install(app, server, db, hand_analytics, daily_quiz, learning_content, admin_console) -> None:
    if getattr(app.state, "jj_operations_learning_installed", False): return
    app.state.jj_operations_learning_installed = True

    @app.get("/api/analysis/learning", include_in_schema=False)
    def analysis_learning(range: str = Query(default="30d", pattern="^(all|7d|30d|90d)$"), user=Depends(server.current_user)):
        return learning_payload(hand_analytics, int(user["id"]), range)

    @app.get("/api/admin/console/operations", include_in_schema=False)
    def operations(user=Depends(server.admin_user)):
        return operations_payload(db)

    @app.get("/api/admin/console/ledger-audit", include_in_schema=False)
    def ledger_audit(limit: int = Query(default=150, ge=1, le=500), kind: str | None = None, user_id: int | None = None, user=Depends(server.admin_user)):
        where, params = ["1=1"], []
        if kind: where.append("l.kind=?"); params.append(kind)
        if user_id: where.append("l.user_id=?"); params.append(user_id)
        params.append(limit)
        deleted = "u.deleted_at" if "deleted_at" in _columns(db, "users") else "NULL"
        with db.connect() as con:
            rows = con.execute(f"""SELECT l.id,l.user_id,l.amount,l.kind,l.reason,l.effective_at,l.created_at,l.reversal_of,
                u.name user_name,COALESCE(NULLIF(u.ranking_name,''),u.name) ranking_name,{deleted} deleted_at,a.name actor_name
                FROM point_ledger l JOIN users u ON u.id=l.user_id LEFT JOIN users a ON a.id=l.created_by
                WHERE {' AND '.join(where)} ORDER BY l.created_at DESC LIMIT ?""", params).fetchall()
        return [dict(r) for r in rows]

    @app.get("/api/home/overview", include_in_schema=False)
    def home_overview(user=Depends(server.current_user)):
        uid = int(user["id"]); ranking_name = str(user.get("ranking_name") or user.get("name") or "")
        rank = next((r for r in admin_console._rankings(db, server, season="fall") if str(r.get("name")) == ranking_name), None)
        summary = hand_analytics._summary_payload(uid, "30d", None)
        hands = hand_analytics._hand_list(uid, limit=3, offset=0, range_name="30d", position=None, result="all", showdown="all", street=None, table_id=None, bookmarked=False, query="")
        day = daily_quiz.today_jst()
        with db.connect() as con: progress = daily_quiz._progress(con, uid, day)
        content = learning_content.get_learning_content()
        return {"points": {"season_total": round(float(rank.get("points",0) if rank else 0),2), "rank": int(rank.get("rank",0)) if rank else None},
                "quiz": {"date": day, **progress},
                "performance": {"hands_30d": int(summary["overall"]["hands"]), "net_bb_30d": float(summary["overall"]["net_bb"]), "bb_per_100": summary["overall"]["bb_per_100"]},
                "learning": learning_payload(hand_analytics, uid, "30d")["recommended"], "recent_hands": hands["items"],
                "articles": list(content.get("articles") or [])[:3]}
