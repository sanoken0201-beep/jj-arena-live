from __future__ import annotations

from datetime import timedelta


def apply(module, db, hand_analytics) -> None:
    if getattr(module, "_jj_v121_hardened", False):
        return
    module._jj_v121_hardened = True

    original_learning = module.learning_payload
    original_anomalies = module._quiz_anomalies
    original_operations = module.operations_payload

    def learning_payload(ha, uid: int, range_name: str):
        payload = original_learning(ha, uid, range_name)
        signals = [x for x in payload.get("signals", []) if x.get("code") != "three_bet_pot_passive"]
        rows = ha._completed_player_rows(uid, range_name)
        hand_ids = {str(r.get("hand_id") or "") for r in rows}
        if hand_ids:
            try:
                with ha._DB.connect() as con:
                    action_rows = con.execute(
                        """SELECT a.hand_id,a.action,a.is_aggressive FROM jj_hand_actions a
                           WHERE a.user_id=? AND a.street<>'preflop'
                             AND a.hand_id IN (
                               SELECT hand_id FROM jj_hand_actions
                               WHERE street='preflop' AND is_aggressive=1
                               GROUP BY hand_id HAVING COUNT(*)>=2
                             )""",
                        (uid,),
                    ).fetchall()
                actions = [
                    dict(r) for r in action_rows
                    if str(r["hand_id"]) in hand_ids
                    and str(r["action"]) in {"check", "call", "raise", "allin_raise", "allin_call"}
                ]
                n = len(actions)
                aggressive = sum(int(r["is_aggressive"] or 0) for r in actions)
                freq = round(aggressive * 100 / n, 1) if n else None
                if n >= 20 and freq is not None and freq <= 25:
                    signals.append({
                        "code": "three_bet_pot_passive",
                        "severity": "watch",
                        "title": "3bet potでpassiveな傾向",
                        "fact": f"指定期間の3bet以上で始まったpotのpostflop {n} actions中、bet/raise系は {aggressive}回（{freq}%）です。",
                        "candidate": "3bet potでCheck/Callへ寄りすぎていないか実ハンドを確認する候補です。",
                        "metric": "3bet-pot aggression",
                        "sample_size": n,
                        "confidence": module._confidence(n),
                        "study_target": "3bet potのCbet / Barrel / Check range",
                        "solver_judgement": False,
                    })
            except Exception:
                pass
        order = {"watch": 0, "info": 1, "ok": 2}
        conf = {"high": 0, "medium": 1, "low": 2}
        signals.sort(key=lambda x: (order.get(x.get("severity"), 9), conf.get(x.get("confidence"), 9), -int(x.get("sample_size") or 0)))
        payload["signals"] = signals[:8]
        if signals:
            payload["recommended"] = signals[0]
        return payload

    def quiz_anomalies(target_db):
        issues = list(original_anomalies(target_db))
        if module._table_exists(target_db, "quiz_daily_answers"):
            since = (module._now() - timedelta(days=8)).isoformat()
            try:
                with target_db.connect() as con:
                    rows = con.execute(
                        """SELECT q.id,q.user_id,q.quiz_date,q.slot,q.answered_at created_at,u.name user_name
                           FROM quiz_daily_answers q JOIN users u ON u.id=q.user_id
                           WHERE q.reward_awarded=10 AND q.answered_at>=?
                             AND NOT EXISTS(
                               SELECT 1 FROM point_ledger l WHERE l.id=('dq3-' || q.id)
                             )
                           ORDER BY q.answered_at DESC LIMIT 30""",
                        (since,),
                    ).fetchall()
                for row in rows:
                    d = dict(row)
                    issues.append({
                        "code": "quiz_answer_without_ledger",
                        "severity": "critical",
                        "user_id": int(d.get("user_id") or 0),
                        "user_name": str(d.get("user_name") or "—"),
                        "detail": f"{d.get('quiz_date')} #{d.get('slot')} は10pt獲得済みですが対応するLedgerがありません。",
                        "detected_at": str(d.get("created_at") or module._now().isoformat()),
                    })
            except Exception:
                pass
        severity = {"critical": 0, "warning": 1, "info": 2}
        issues.sort(key=lambda x: (severity.get(x.get("severity"), 9), str(x.get("detected_at") or "")), reverse=False)
        return issues[:80]

    def operations_payload(target_db):
        payload = original_operations(target_db)
        participants = 0
        try:
            start_date = (module._now().astimezone(module.JST).date() - timedelta(days=6)).isoformat()
            with target_db.connect() as con:
                row = con.execute(
                    "SELECT COUNT(DISTINCT name) c FROM entries WHERE date>=? AND name<>'運営調整'",
                    (start_date,),
                ).fetchone()
            participants = int(row["c"] or 0)
        except Exception:
            participants = 0
        payload.setdefault("activity", {})["participants_7d"] = participants
        return payload

    module.learning_payload = learning_payload
    module._quiz_anomalies = quiz_anomalies
    module.operations_payload = operations_payload
