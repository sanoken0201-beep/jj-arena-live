from __future__ import annotations

from pathlib import Path

from player_ux_asset_transform import PLAYER_UX_MARKER, transform_app_js


ROOT = Path(__file__).resolve().parent


def main() -> None:
    original = (ROOT / "materialized_v1244" / "static" / "app.js").read_text(encoding="utf-8")
    patched = transform_app_js(original)

    # Deterministic transform / drift contract.
    assert PLAYER_UX_MARKER in patched
    assert patched != original
    assert transform_app_js(patched) == patched

    # P1-01: every action that actually consumes the remaining stack, including
    # CALL, goes through one confirmation rule tied to table/hand/turn/deadline.
    assert "const commitChips=action==='call'?" in patched
    assert "const commitsAllin=heroStack>0&&commitChips>=heroStack-0.01" in patched
    assert "追加 ${safe(jjV124FmtNumber(commitBb,1))}bb ／ 残り0bb" in patched
    assert "${currentTableId||''}:${hand.id||''}:${hand.action_seat??''}:${hand.action_deadline||''}" in patched
    assert "const commitsAllin=action==='allin'||(action==='raise'&&atMax);" not in patched

    # P1-02: draft amount is external to the DOM, survives same-decision render,
    # permits blank/partial text, restores focus, and validates only on commit.
    assert "let jjV124RaiseDraft={key:'',text:'',value:null,notice:''}" in patched
    assert "function jjV124DecisionKey()" in patched
    assert "type=\"text\" inputmode=\"decimal\" autocomplete=\"off\"" in patched
    assert "jjV124ParseRaiseText" in patched
    assert "next.focus({preventScroll:true})" in patched
    assert "setSelectionRange(focusDraft.start,focusDraft.end)" in patched
    assert "ベット／レイズ額を入力してください" in patched
    assert "利用可能額が変わったため" in patched

    # P1-03: BET is reserved for an unbet postflop street. Otherwise the action
    # is RAISE, and the button distinguishes raise-to total from added chips.
    assert "const isBet=phase!=='preflop'&&currentBet<=0" in patched
    assert "${meta.en} · +${jjV185FmtBb(added)}" in patched
    assert "${meta.ja} 合計 ${jjV185FmtBb(raiseAmount)}" in patched

    # P1-04: no integer ceiling in the decision stack; HU effective exposure
    # includes the call already in front, while multiway refuses one fake number.
    assert "const stack=jjV124RawBb(hero?.stack||0,{maxDecimals:1});" in patched
    assert "if(opponents.length!==1)return null" in patched
    assert "call+Number(opponents[0].stack||0)" in patched
    assert "effectiveChips==null?'相手別'" in patched
    assert "Math.ceil(Number(chips||0)/big)" not in patched

    # P2-05 / P2-06 / P2-11: the final lobby owns results/stat states, seating has
    # one main CTA on the table, and the final lobby labels are Japanese-first.
    tail = patched.split("// v1.16.2 unmistakable primary seating.", 1)[1]
    assert "結果を読み込み中" in tail
    assert "統計を読み込み中" in tail
    assert "api('/online/results?limit=72')" in tail
    assert "api('/online/summary')" in tail
    assert "data-jj-online-retry" in tail
    assert "累計レーキ（卓全体）" in tail
    assert "卓中央の「150bbで着席」" in tail
    assert 'id="jjJoinTableBtn">150bbで着席</button>' in tail
    assert "'● 対戦中':'参加受付中'" in tail

    # Cache ownership belongs to the production integration shim. Later audit
    # phases may bump the version while preserving every Phase 1 behavior.
    entry = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "'/static/app.js?v=" in entry
    assert "jj-arena-live-v" in entry
    assert 'path == "/static/app.js"' in entry
    assert "transform_app_js(js)" in entry
    assert ">チャット<" in entry and ">ハンド履歴<" in entry and "← ロビー" in entry

    print("JJ_PLAYER_UX_AUDIT_SMOKE_OK")


if __name__ == "__main__":
    main()
