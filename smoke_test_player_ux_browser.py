from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from player_ux_asset_transform import transform_app_js


ROOT = Path(__file__).resolve().parent


def _slice(source: str, start: str, end: str) -> str:
    a = source.index(start)
    b = source.index(end, a)
    return source[a:b]


def _chrome() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    raise AssertionError("Chrome/Chromium is required for player UX browser regression")


def _fixture() -> str:
    original = (ROOT / "materialized_v1244" / "static" / "app.js").read_text(encoding="utf-8")
    source = transform_app_js(original)

    key_js = _slice(source, "  function jjV123AllinKey", "\n\n  function jjV123SuitName")
    sync_js = _slice(source, "  function jjV185SyncRaiseUi", "\n\n  renderActionBar=function(){")
    v124_js = _slice(source, "  const JJ_V124_STREET", "\n  // Desktop bet markers")
    allin_js = _slice(source, "  // All-in is deliberately", "\n\n  // Unlock WebAudio")

    setup = r'''
const $=(sel,root=document)=>root.querySelector(sel);
const safe=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const suitChar=c=>({c:'♣',d:'♦',h:'♥',s:'♠'})[c]||'';
let currentTableId='jj-table-a';
let me={id:1};
let tableState={
  big_blind:100,
  status:'playing',
  hand:{id:'hand-1',phase:'preflop',action_seat:0,action_deadline:'2026-09-12T06:10:00Z',current_bet:200,board:[]},
  legal:{can_act:true,can_check:false,can_call:true,can_raise:true,can_all_in:true,call_amount:100,min_raise_to:300,max_raise_to:10000},
  seats:[
    {user_id:1,seat:0,stack:10000,round_bet:100,contributed:100,in_hand:true,folded:false,cards:['As','Kh']},
    {user_id:2,seat:1,stack:10000,round_bet:200,contributed:200,in_hand:true,folded:false,cards:['??','??']},
  ],
};
function jjTotalPot(){return (tableState.seats||[]).reduce((s,p)=>s+Number(p.contributed||0),0)}
function jjRaiseBounds(){const l=tableState.legal||{},big=Number(tableState.big_blind||100);return {min:Number(l.min_raise_to||l.max_raise_to||0)/big,max:Number(l.max_raise_to||0)/big}}
function jjClampRaiseBb(v){const b=jjRaiseBounds();return Math.max(b.min,Math.min(b.max,Number(v||b.min)))}
function jjPotPctBb(pct){const hero=tableState.seats.find(p=>p.user_id===me.id),l=tableState.legal||{},big=Number(tableState.big_blind||100),call=Number(l.call_amount||0),pot=jjTotalPot(),round=Number(hero?.round_bet||0);return jjClampRaiseBb((round+call+(pot+call)*(Number(pct)/100))/big)}
function jjV185FmtBb(v){const n=Number(v||0),rounded=Math.round(n*100)/100;return `${Number.isInteger(rounded)?rounded:rounded.toFixed(rounded*10%1?2:1)}bb`}
function jjSetRaiseBb(v){const value=jjClampRaiseBb(v),input=$('#raiseTo'),slider=$('#raiseSlider');if(input)input.value=String(value);if(slider)slider.value=String(value)}
function jjV123Pending(){return false}
function jjV123Tone(){}
function jjV123Haptic(){}
function jjV123ActionState(){}
function jjV123ClockFeedback(){}
let jjV123AllinConfirmUntil=0;
let jjV123AllinConfirmKey='';
'''

    tests = r'''
async function frame(){await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))}
function assert(cond,message){if(!cond)throw new Error(message)}
async function run(){
  renderActionBar();
  let input=$('#raiseTo'),slider=$('#raiseSlider');
  assert(input&&slider,'sizing controls rendered');

  // Editing may be temporarily blank. It must not clamp back to the minimum.
  input.focus();input.setSelectionRange(0,input.value.length);input.value='';input.dispatchEvent(new Event('input',{bubbles:true}));
  assert(input.value==='','blank draft is preserved');
  assert($('#jjV124SizingError').textContent.includes('金額を入力'),'blank draft explains validation');

  // A valid custom size synchronizes slider and action labels.
  input.value='7.5';input.dispatchEvent(new Event('input',{bubbles:true}));input.focus();input.setSelectionRange(3,3);
  assert(input.value==='7.5','custom amount accepted');
  assert(slider.value==='7.5','slider follows typed amount');
  assert($('#jjRaiseAction b').textContent.includes('合計 7.5bb'),'raise button shows raise-to total');
  assert($('#jjRaiseAction small').textContent.includes('+6.5bb'),'raise button shows incremental chips');

  // A same-decision state update may redraw the bar, but draft and focus survive.
  tableState.seats[1].contributed=250;
  renderActionBar();await frame();
  input=$('#raiseTo');slider=$('#raiseSlider');
  assert(input.value==='7.5','same-turn rerender preserves amount');
  assert(slider.value==='7.5','same-turn rerender preserves slider');
  assert(document.activeElement===input,'same-turn rerender restores focus');

  // A new decision invalidates the previous draft.
  tableState.hand.action_deadline='2026-09-12T06:10:45Z';
  renderActionBar();await frame();
  assert($('#raiseTo').value==='3','new decision resets draft to legal minimum');

  // Preflop BB option is RAISE even when checking is free.
  tableState.legal={...tableState.legal,can_check:true,can_call:false,call_amount:0,min_raise_to:300,max_raise_to:10000};
  tableState.hand.phase='preflop';tableState.hand.current_bet=200;
  renderActionBar();
  assert($('#jjRaiseAction small').textContent.startsWith('RAISE'),'preflop free option is raise, not bet');
  assert($('#jjRaiseAction b').textContent.startsWith('レイズ'),'preflop Japanese verb is raise');

  // Only an unopened postflop street is a BET.
  tableState.hand.phase='flop';tableState.hand.current_bet=0;tableState.hand.action_deadline='2026-09-12T06:11:30Z';
  tableState.legal={...tableState.legal,min_raise_to:100,max_raise_to:10000};
  renderActionBar();
  assert($('#jjRaiseAction small').textContent.startsWith('BET'),'unopened flop uses bet');
  assert($('#jjRaiseAction b').textContent.startsWith('ベット'),'unopened flop Japanese verb is bet');

  // Stack precision and HU effective exposure remain meaningful vs an all-in opponent.
  const hero=tableState.seats[0],villain=tableState.seats[1];
  hero.stack=1010;hero.round_bet=0;villain.stack=0;villain.round_bet=500;villain.in_hand=true;villain.folded=false;
  tableState.hand.current_bet=500;tableState.hand.action_deadline='2026-09-12T06:12:15Z';
  tableState.legal={can_act:true,can_check:false,can_call:true,can_raise:false,can_all_in:false,call_amount:500,min_raise_to:0,max_raise_to:0};
  renderActionBar();
  const meta=[...document.querySelectorAll('.jj-v124-decision-meta>div')].map(x=>x.textContent.trim());
  assert(meta.some(x=>x==='STACK10.1bb'),'10.1bb stack is not rounded up to 11bb');
  assert(meta.some(x=>x==='EFFECTIVE5bb'),'HU effective exposure includes amount already facing hero');

  // Multiway pots do not present one misleading effective-stack number.
  tableState.seats.push({user_id:3,seat:2,stack:2000,round_bet:0,contributed:0,in_hand:true,folded:false,cards:['??','??']});
  renderActionBar();
  assert([...document.querySelectorAll('.jj-v124-decision-meta strong')].some(x=>x.textContent==='相手別'),'multiway effective display is explicitly per-opponent');
  tableState.seats.pop();

  // All-in CALL uses the same two-step confirmation as all-in raises.
  hero.stack=500;hero.round_bet=0;villain.stack=0;villain.round_bet=500;
  tableState.hand.phase='river';tableState.hand.current_bet=500;tableState.hand.action_deadline='2026-09-12T06:13:00Z';
  tableState.legal={can_act:true,can_check:false,can_call:true,can_raise:false,can_all_in:false,call_amount:500,min_raise_to:0,max_raise_to:0};
  let sent=0;
  $('#actionBar').addEventListener('click',e=>{if(e.target.closest('[data-action]'))sent++});
  renderActionBar();
  let callBtn=$('#actionBar [data-action="call"]');
  callBtn.click();
  assert(sent===0,'first all-in call tap is confirmation only');
  assert(callBtn.textContent.includes('追加 5bb')&&callBtn.textContent.includes('残り0bb'),'confirmation shows commitment and remaining stack');

  // A changed turn/deadline invalidates that confirmation.
  tableState.hand.action_deadline='2026-09-12T06:13:45Z';renderActionBar();
  callBtn=$('#actionBar [data-action="call"]');callBtn.click();
  assert(sent===0,'state change invalidates old all-in confirmation');
  callBtn.click();
  assert(sent===1,'second tap on unchanged decision proceeds exactly once');
}
run().then(()=>{
  document.body.insertAdjacentHTML('beforeend','<pre id="result" data-player-ux-ok="1">ok</pre>');
}).catch(err=>{
  document.body.insertAdjacentHTML('beforeend',`<pre id="result" data-player-ux-ok="0">${safe(err.stack||err.message||err)}</pre>`);
});
'''

    return (
        "<!doctype html><html lang=\"ja\"><head><meta charset=\"utf-8\"></head><body>"
        '<div id="actionBar"></div><script>'
        + setup
        + key_js
        + "\n"
        + sync_js
        + "\n"
        + v124_js
        + "\n"
        + allin_js
        + "\n"
        + tests
        + "</script></body></html>"
    )


def main() -> None:
    chrome = _chrome()
    with tempfile.TemporaryDirectory() as td:
        fixture = Path(td) / "player-ux-browser.html"
        fixture.write_text(_fixture(), encoding="utf-8")
        proc = subprocess.run(
            [
                chrome,
                "--headless",
                "--no-sandbox",
                "--disable-gpu",
                "--allow-file-access-from-files",
                "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=5000",
                "--window-size=390,844",
                "--dump-dom",
                fixture.resolve().as_uri(),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        assert 'data-player-ux-ok="1"' in proc.stdout, proc.stdout[-3500:] + "\n" + proc.stderr[-1500:]
    print("JJ_PLAYER_UX_BROWSER_OK")


if __name__ == "__main__":
    main()
