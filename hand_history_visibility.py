from __future__ import annotations

"""Participant-only completed-hand history visibility.

The live poker engine keeps opponent hole cards private. This extension changes
only the post-hand review surface: once a hand is complete, a participant may
review every player's stored hole cards, every recorded action and the board.
Users who did not participate continue to receive the existing 404 response.
"""

from typing import Any


HAND_HISTORY_VISIBILITY_MARKER = "participant hand history visibility 2026-09-12"


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"hand history visibility transform drift at {label}: "
            f"expected 1 source block, found {count}"
        )
    return source.replace(old, new, 1)


def install(analytics) -> None:
    """Reveal stored cards only after the existing participant access check.

    ``hand_analytics._detail_payload`` already enforces that ``viewer_id`` is a
    row in ``jj_hand_players`` for the requested hand. We intentionally call the
    original function first and only query raw cards after it succeeds. Active
    hands remain masked, so knowing a current hand id cannot expose live cards.
    """

    if getattr(analytics, "_jj_participant_hand_history_installed", False):
        return

    original_detail = analytics._detail_payload
    original_export = getattr(analytics, "_export_text", None)

    def participant_detail(hand_id: str, viewer_id: int) -> dict[str, Any]:
        data = original_detail(hand_id, viewer_id)
        hand = data.get("hand") or {}
        if not hand.get("completed_at"):
            return data

        with analytics._DB.connect() as con:
            rows = con.execute(
                "SELECT user_id,hole_cards_json FROM jj_hand_players WHERE hand_id=? ORDER BY seat",
                (hand_id,),
            ).fetchall()

        cards_by_user: dict[int, list[str]] = {}
        for row in rows:
            record = dict(row)
            cards_by_user[int(record["user_id"])] = list(
                analytics._loads(record.get("hole_cards_json"), [])
            )

        for player in data.get("players") or []:
            uid = int(player["user_id"])
            if uid in cards_by_user:
                player["cards"] = cards_by_user[uid]

        data["visibility"] = {
            "scope": "participant",
            "completed_hand_cards": "all_players",
        }
        return data

    analytics._detail_payload = participant_detail

    if callable(original_export):
        def participant_export(hand_id: str, viewer_id: int) -> str:
            text = original_export(hand_id, viewer_id)
            data = analytics._detail_payload(hand_id, viewer_id)
            if not (data.get("hand") or {}).get("completed_at"):
                return text
            opponent_lines = []
            for player in data.get("players") or []:
                if int(player["user_id"]) == int(viewer_id):
                    continue
                cards = list(player.get("cards") or [])
                if cards:
                    opponent_lines.append(
                        f"Recorded hand for {player.get('player_name')}: [{' '.join(cards)}]"
                    )
            if not opponent_lines:
                return text
            marker = "*** HOLE CARDS ***\n"
            if marker not in text:
                return text
            return text.replace(marker, marker + "\n".join(opponent_lines) + "\n", 1)

        analytics._export_text = participant_export

    analytics._jj_participant_hand_history_installed = True


def transform_app_js(source: str) -> str:
    """Make completed-hand review show every participant's hand and action flow."""

    if HAND_HISTORY_VISIBILITY_MARKER in source:
        return source

    source = _replace_once(
        source,
        """  function jjRenderReplayStage(state,players,heroId){const box=$('#jjReplayStage');if(!box)return;if(!state?.hand){box.innerHTML='<div class=\"empty\">リプレイ用スナップショットがありません</div>';return}const cardsById=new Map(players.map(p=>[Number(p.user_id),p.cards||[]])),seats=state.seats||[],max=6,phase=String(state.hand.phase||'').toLowerCase(),showdownVisible=phase==='complete';box.innerHTML=`<div class=\"jj-replay-table\"><div class=\"jj-replay-center\"><div class=\"cards\">${jjCardSet(state.hand.board||[])}</div><b>${safe(String(state.hand.phase||'').toUpperCase())}</b></div>${seats.map(p=>{const angle=(-90+Number(p.seat||0)*(360/max))*Math.PI/180,left=50+Math.cos(angle)*41,top=49+Math.sin(angle)*37,cards=cardsById.get(Number(p.user_id))||[],hero=Number(p.user_id)===Number(heroId),revealed=showdownVisible&&cards.some(c=>c!=='??'),shown=hero?cards:revealed?cards:(p.in_hand?['??','??']:[]);return `<div class=\"jj-replay-seat ${hero?'hero':''} ${p.folded?'folded':''}\" style=\"left:${left}%;top:${top}%\"><strong>${safe(p.name)}</strong><span>${(Number(p.stack||0)/Math.max(1,Number(state.big_blind||100))).toFixed(1)}bb</span>${shown.length?`<div class=\"cards jj-tiny-cards\">${jjCardSet(shown)}</div>`:''}</div>`}).join('')}</div>`}
""",
        """  function jjRenderReplayStage(state,players,heroId){const box=$('#jjReplayStage');if(!box)return;if(!state?.hand){box.innerHTML='<div class=\"empty\">リプレイ用スナップショットがありません</div>';return}const cardsById=new Map(players.map(p=>[Number(p.user_id),p.cards||[]])),seats=state.seats||[],max=6;box.innerHTML=`<div class=\"jj-replay-table\"><div class=\"jj-replay-center\"><div class=\"cards\">${jjCardSet(state.hand.board||[])}</div><b>${safe(String(state.hand.phase||'').toUpperCase())}</b></div>${seats.map(p=>{const angle=(-90+Number(p.seat||0)*(360/max))*Math.PI/180,left=50+Math.cos(angle)*41,top=49+Math.sin(angle)*37,cards=cardsById.get(Number(p.user_id))||[],hero=Number(p.user_id)===Number(heroId),shown=cards;return `<div class=\"jj-replay-seat ${hero?'hero':''} ${p.folded?'folded':''}\" style=\"left:${left}%;top:${top}%\"><strong>${safe(p.name)}</strong><span>${(Number(p.stack||0)/Math.max(1,Number(state.big_blind||100))).toFixed(1)}bb</span>${shown.length?`<div class=\"cards jj-tiny-cards\">${jjCardSet(shown)}</div>`:''}</div>`}).join('')}</div>`}
""",
        "completed-hand replay cards",
    )

    source = _replace_once(
        source,
        """      <section class=\"jj-v122-cards-zone\">
        <div class=\"jj-v122-hero-hand\"><span>YOUR HAND</span><div class=\"cards\">${jjCardSet(hero.cards)}</div></div>
        <div class=\"jj-v122-board\"><span>BOARD</span><div class=\"cards\">${jjCardSet(h.board)}</div></div>
      </section>
""",
        """      <section class=\"jj-v122-cards-zone\">
        <div class=\"jj-v122-hero-hand jj-hand-participant-hands\"><span>ALL HANDS</span><div class=\"jj-hand-participant-grid\">${players.map(p=>{const mine=Number(p.user_id)===Number(me.id);return `<article class=\"jj-hand-participant ${mine?'is-hero':''}\"><small>${mine?'YOU':safe(p.player_name||'PLAYER')}</small><div class=\"cards\">${jjCardSet(p.cards)}</div></article>`}).join('')}</div></div>
        <div class=\"jj-v122-board\"><span>BOARD</span><div class=\"cards\">${jjCardSet(h.board)}</div></div>
      </section>
""",
        "review all participant hands",
    )

    source = _replace_once(
        source,
        "<p class=\"jj-v122-privacy\">相手のホールカードは、ショーダウンで実際に公開された場合だけ表示します。</p>",
        "<p class=\"jj-v122-privacy\">この履歴は自分が参加したハンドだけ表示します。終了済みハンドでは、全プレイヤーのホールカード・全アクション・ボードを確認できます。</p>",
        "review privacy copy",
    )

    source = _replace_once(
        source,
        "<p class=\"hint\">相手のホールカードはショーダウンで公開された場合だけ表示します。通常のフォールドハンドでは確認できません。</p>",
        "<p class=\"hint\">履歴は参加したハンドだけ閲覧できます。終了後は参加者全員のホールカード、アクション、ボードを確認できます。</p>",
        "legacy review privacy copy",
    )

    source = _replace_once(
        source,
        "オンライン卓で確定した自分のハンドだけを記録します。統計はGTO判定ではなく、実際のプレイ頻度と収支の傾向です。",
        "オンライン卓で自分が参加して確定したハンドだけを記録します。各履歴では参加者全員のハンド・アクション・ボードを確認できます。統計はGTO判定ではなく、実際のプレイ頻度と収支の傾向です。",
        "analysis privacy description",
    )

    return source.rstrip() + f"\n// {HAND_HISTORY_VISIBILITY_MARKER}\n"


def transform_styles(source: str) -> str:
    if HAND_HISTORY_VISIBILITY_MARKER in source:
        return source
    css = r'''

/* participant hand history visibility 2026-09-12 */
.jj-hand-participant-hands{min-width:0}
.jj-hand-participant-grid{display:flex;flex-wrap:wrap;gap:.65rem;margin-top:.45rem}
.jj-hand-participant{display:grid;gap:.35rem;min-width:104px;padding:.55rem .65rem;border:1px solid rgba(255,255,255,.12);border-radius:12px;background:rgba(255,255,255,.035)}
.jj-hand-participant>small{font-size:.68rem;font-weight:800;letter-spacing:.08em;opacity:.78}
.jj-hand-participant.is-hero{border-color:rgba(106,225,170,.52);background:rgba(106,225,170,.08)}
.jj-hand-participant .cards{display:flex;gap:.3rem;flex-wrap:nowrap}
@media(max-width:760px){
  .jj-hand-participant-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.5rem}
  .jj-hand-participant{min-width:0;padding:.5rem}
}
'''
    return source.rstrip() + css + "\n"
