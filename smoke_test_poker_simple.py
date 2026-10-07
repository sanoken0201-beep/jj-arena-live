from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
import shutil
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright
from served_assets import build_all, ASSET_VERSION

ROOT = Path(__file__).resolve().parent
HOOKS = r'''
  // Test-only injection: never included in served assets.
  const testSent=[];
  let testResolve=null,testReject=null;
  window.JJ_TEST={
    sent:testSent,
    setState(s){me={id:1,name:'Hero',role:'member'};currentTableId='jj-table-a';tableState=structuredClone(s);tableMessages=[];jjV2AcceptState('ws',null);renderPokerRoom()},
    setObserverState(s){me={id:99,name:'Observer',role:'member'};currentTableId='jj-table-a';tableState=structuredClone(s);tableMessages=[];jjV2AcceptState('ws',null);renderPokerRoom()},
    render(){renderPokerRoom()},
    pending(){return jjV121ActionPending},
    defer(){post=async (path,body)=>{testSent.push({path,body});return await new Promise((resolve,reject)=>{testResolve=resolve;testReject=reject})}},
    resolve(s){testResolve(structuredClone(s))},
    reject(){testReject(new Error('test rejection'))},
    recoverWith(s){api=async ()=>({state:structuredClone(s),messages:[]})},
    stale(){jjV2SetConnection('reconnecting',false)},
    reserve(mode){jjV5SetPreAction(mode)},
    state(){return tableState},
    switchTable(){currentTableId='jj-table-b'},
  };
  document.getElementById('authView').classList.add('hidden');
  document.getElementById('appView').classList.remove('hidden');
  document.querySelectorAll('.view').forEach(el=>el.classList.remove('active-view'));
  document.getElementById('tablesView').classList.add('active-view');
  document.getElementById('lobbyPanel').classList.add('hidden');
  document.getElementById('pokerRoom').classList.remove('hidden');
'''

def state(check=False, waiting=False, players=2):
    seats = [{"user_id":1,"seat":0,"name":"Hero","stack":14950,"round_bet":50,"contributed":50,"in_hand":True,"folded":False,"cards":["2h","6h"],"ready":True}]
    for i in range(1,players):
        seats.append({"user_id":i+1,"seat":i,"name":"Player "+str(i),"stack":14900,"round_bet":100 if i==1 else 0,"contributed":100 if i==1 else 0,"in_hand":True,"folded":False,"cards":["??","??"],"ready":True})
    return {"id":"jj-table-a","name":"JJ Table A","max_seats":6,"status":"playing","session_active":True,"big_blind":100,"small_blind":50,"button_seat":0,"seats":seats,
        "hand":{"id":"visibility-hand","phase":"preflop","action_seat":1 if waiting else 0,"action_deadline":(datetime.now(timezone.utc)+timedelta(seconds=45)).isoformat(),"board":[],"current_bet":100,"log":["Player 1 posts 1bb","Hero calls 1bb","Player 2 raises to 4bb"]},
        "legal":{"can_act":not waiting,"can_check":check,"can_call":not check,"can_raise":not waiting,"can_all_in":not waiting,"call_amount":0 if check else 50,"min_raise_to":200,"max_raise_to":15000},"last_result":None}

def main():
    chrome = next((shutil.which(n) for n in ("google-chrome","google-chrome-stable","chrome","chromium","chromium-browser","msedge") if shutil.which(n)),None)
    assert chrome, "Chrome is required"
    artifacts=ROOT/"test-artifacts"/"poker-simple"
    artifacts.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as td, sync_playwright() as p:
        root=Path(td)
        build_all(root)
        js=(root/"static/app.js").read_text(encoding="utf-8")
        assert js.count("  init();")==1
        js=js.replace("  init();","  bind();",1)
        end=js.rfind("})();")
        js=js[:end]+HOOKS+js[end:]
        (root/"static/app.js").write_text(js,encoding="utf-8")
        html=(root/"index.html").read_text(encoding="utf-8").replace('"/static/','"static/')
        (root/"index.html").write_text(html,encoding="utf-8")
        browser=p.chromium.launch(executable_path=chrome,headless=True,args=["--no-sandbox","--allow-file-access-from-files"])
        for width,height in ((390,664),(360,640),(390,844),(844,390),(1366,768),(1024,768)):
            page=browser.new_page(viewport={"width":width,"height":height})
            errors=[]
            page.on("pageerror",lambda err:errors.append(str(err)))
            page.goto((root/"index.html").as_uri())
            page.wait_for_function("!!window.JJ_TEST")
            for players in (2,6):
                for waiting in (False,True):
                    s=state(waiting=waiting,players=players)
                    page.evaluate("s=>JJ_TEST.setState(s)",s)
                    page.locator(".jj-v7-hand .card-face").first.wait_for(state="visible")
                    # Full hand glyphs must be above/inside the dock, never covered.
                    visible=page.evaluate("""() => {
                      const cards=[...document.querySelectorAll('.jj-v7-hand .card-face')];
                      return cards.length===2&&cards.every(c=>{
                        const r=c.getBoundingClientRect(),target=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
                        return r.width>=30&&r.height>=40&&r.top>=0&&r.bottom<=innerHeight&&!!target&&c.contains(target);
                      });
                    }""")
                    # On short landscape screens, scrolling is intentional and controls remain reachable.
                    if height>=600:
                        assert visible, (width,height,players,waiting,"hand occluded")
                    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+2"),"horizontal overflow"
                    assert page.locator(".jj-v124-decision-meta").count()==0
                    assert page.locator("#jjV7Menu").count()==1
                    if width<=390 and height>=640 and players==6:
                        opponent_cards=page.evaluate("""() => {
                          const table=document.getElementById('pokerTable').getBoundingClientRect();
                          const cards=[...document.querySelectorAll('.jj-seat:not(.is-hero) .jj-hole .card-face')];
                          const seats=[...document.querySelectorAll('.jj-seat:not(.is-hero)[data-jj-visual]')];
                          const details=cards.map(card=>{
                            const r=card.getBoundingClientRect(),target=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2),hole=card.closest('.jj-hole'),seat=card.closest('.jj-seat');
                            const hs=hole?getComputedStyle(hole):null,cs=getComputedStyle(card);
                            return {visual:seat?.dataset.jjVisual||'',rect:{left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height},target:target?.className||target?.id||target?.tagName||'',hole:{display:hs?.display,position:hs?.position,z:hs?.zIndex,top:hs?.top,left:hs?.left,transform:hs?.transform},card:{display:cs.display,visibility:cs.visibility,opacity:cs.opacity,z:cs.zIndex}};
                          });
                          const visible=cards.length===10&&details.every(d=>{
                            const r=d.rect;
                            return r.width>=32&&r.height>=44&&r.top>=table.top-1&&r.bottom<=table.bottom+1&&r.left>=table.left-1&&r.right<=table.right+1&&String(d.target).includes('card-face');
                          });
                          const xs=seats.map(s=>s.getBoundingClientRect().left+s.getBoundingClientRect().width/2);
                          return {visible,spread:xs.length===5&&(Math.max(...xs)-Math.min(...xs))>=table.width*.60,topSeat:!!document.querySelector('.jj-seat[data-jj-visual="3"] .jj-hole .card-face'),table:{left:table.left,top:table.top,right:table.right,bottom:table.bottom,width:table.width,height:table.height},details};
                        }""")
                        assert opponent_cards["visible"],(width,height,players,waiting,"opponent cards clipped",opponent_cards)
                        assert opponent_cards["spread"],(width,height,players,waiting,"opponent seats collapsed",opponent_cards)
                        assert opponent_cards["topSeat"],(width,height,players,waiting,"opposite hand missing")
                    page.screenshot(path=str(artifacts/f"{width}x{height}-{players}-{'wait' if waiting else 'act'}.png"))
            if width<=390 and height>=640:
                layout_cases=[]
                for name,waiting,phase,board_count,result,all_in in (
                    ("waiting",True,"river",5,False,False),
                    ("can-act",False,"river",5,False,False),
                    ("showdown",True,"complete",5,True,False),
                    ("all-in-runout",True,"turn",4,False,True),
                ):
                    s=state(waiting=waiting,players=6)
                    s["hand"]["phase"]=phase
                    s["hand"]["board"]=["2c","7d","Jh","Qs","Ac"][:board_count]
                    if phase=="complete":
                        s["hand"]["action_seat"]=None
                        s["hand"]["action_deadline"]=None
                    if result:
                        s["last_result"]={"message":"ヨシハル +9bb (One Pair)","net_results":[]}
                    if all_in:
                        s["hand"]["action_seat"]=None
                        s["hand"]["action_deadline"]=None
                        s["legal"]={"can_act":False,"can_check":False,"can_call":False,"can_raise":False,"can_all_in":False,"call_amount":0,"min_raise_to":0,"max_raise_to":0}
                        for seat in s["seats"]:
                            seat["all_in"]=True
                    layout_cases.append((name,s))
                for name,s in layout_cases:
                    page.evaluate("s=>JJ_TEST.setState(s)",s)
                    geometry=page.evaluate("""() => {
                      const intersects=(a,b)=>!(a.right<=b.left||a.left>=b.right||a.bottom<=b.top||a.top>=b.bottom);
                      const table=document.querySelector('#pokerTable').getBoundingClientRect();
                      const board=[...document.querySelectorAll('#boardCards .card-face')].map(x=>x.getBoundingClientRect());
                      const seats=[...document.querySelectorAll('#pokerTable .jj-seat')].map(x=>({visual:x.dataset.jjVisual,rect:x.querySelector('.jj-seat-box').getBoundingClientRect()}));
                      const bar=document.querySelector('#actionBar').getBoundingClientRect();
                      const metric=r=>({left:Math.round(r.left),top:Math.round(r.top),right:Math.round(r.right),bottom:Math.round(r.bottom)});
                      return {
                        boardCount:board.length,
                        boardVisible:board.every(r=>r.left>=table.left-1&&r.right<=table.right+1&&r.top>=table.top-1&&r.bottom<=table.bottom+1),
                        boardClear:board.every(card=>seats.every(seat=>!intersects(card,seat.rect))),
                        overlaps:board.flatMap((card,cardIndex)=>seats.filter(seat=>intersects(card,seat.rect)).map(seat=>({card:cardIndex+1,visual:seat.visual,cardRect:metric(card),seatRect:metric(seat.rect)}))),
                        actionHeight:bar.height,
                        resultClear:document.querySelector('#resultBanner').classList.contains('hidden')||!intersects(document.querySelector('#resultBanner').getBoundingClientRect(),table),
                      };
                    }""")
                    assert geometry["boardCount"] in (4,5),(width,height,name,geometry)
                    assert geometry["boardVisible"],(width,height,name,"board clipped",geometry)
                    assert geometry["boardClear"],(width,height,name,"board covered by player info",geometry)
                    assert geometry["resultClear"],(width,height,name,"result covers table",geometry)
                    assert geometry["actionHeight"]<=320,(width,height,name,"action panel too tall",geometry)

                observer=state(waiting=True,players=6)
                observer["seats"]=[seat for seat in observer["seats"] if seat["seat"]!=3]
                observer["hand"].update({"phase":"complete","action_seat":None,"action_deadline":None,"board":["2c","7d","Jh","Qs","Ac"]})
                observer["last_result"]={"message":"ヨシハル +9bb (One Pair)","net_results":[]}
                names={0:"ヨシハル",1:"ユウイチ",2:"Player 2",4:"Player 4",5:"トモリ"}
                cards={0:["Qh","Ts"],1:["As","Jd"],2:["9c","9d"],4:["8s","7s"],5:["Ad","Qc"]}
                for seat in observer["seats"]:
                    seat["name"]=names[seat["seat"]]
                    seat["cards"]=cards[seat["seat"]]
                page.evaluate("s=>JJ_TEST.setObserverState(s)",observer)
                page.locator("#jjObserverJoin button").wait_for(state="visible")
                assert page.locator("#jjObserverJoin button").inner_text().strip()=="150bbで着席"
                observer_geometry=page.evaluate("""() => {
                  const intersects=(a,b)=>!(a.right<=b.left||a.left>=b.right||a.bottom<=b.top||a.top>=b.bottom);
                  const table=document.querySelector('#pokerTable').getBoundingClientRect();
                  const room=document.querySelector('#pokerRoom').getBoundingClientRect();
                  const layout=document.querySelector('#pokerRoom .poker-layout').getBoundingClientRect();
                  const zone=document.querySelector('#pokerRoom .poker-zone').getBoundingClientRect();
                  const board=[...document.querySelectorAll('#boardCards .card-face')].map(x=>x.getBoundingClientRect());
                  const seats=[...document.querySelectorAll('#pokerTable .jj-seat-box')].map(x=>x.getBoundingClientRect());
                  const bottom=document.querySelector('.jj-seat[data-jj-visual="0"] .stack');
                  const stack=bottom.getBoundingClientRect(),join=document.querySelector('#jjObserverJoin').getBoundingClientRect();
                  const target=document.elementFromPoint(stack.left+stack.width/2,stack.top+stack.height/2);
                  return {
                    boardCount:board.length,
                    boardVisible:board.every(r=>r.left>=table.left-1&&r.right<=table.right+1&&r.top>=table.top-1&&r.bottom<=table.bottom+1),
                    boardClear:board.every(card=>seats.every(seat=>!intersects(card,seat))),
                    bottomStackVisible:stack.top>=table.top&&stack.bottom<=table.bottom&&bottom.contains(target),
                    joinClearOfBottom:!intersects(stack,join),
                    joinCompact:join.width<=160&&join.height<=50,
                    tableFillsObserver:table.bottom>=innerHeight-2,
                    metrics:{innerHeight,room:{top:room.top,bottom:room.bottom,height:room.height},layout:{top:layout.top,bottom:layout.bottom,height:layout.height},zone:{top:zone.top,bottom:zone.bottom,height:zone.height},table:{top:table.top,bottom:table.bottom,height:table.height}},
                  };
                }""")
                assert observer_geometry["boardCount"]==5,(width,height,"observer board incomplete",observer_geometry)
                assert observer_geometry["boardVisible"],(width,height,"observer board clipped",observer_geometry)
                assert observer_geometry["boardClear"],(width,height,"observer board covered by player info",observer_geometry)
                assert observer_geometry["bottomStackVisible"],(width,height,"bottom player stack hidden",observer_geometry)
                assert observer_geometry["joinClearOfBottom"],(width,height,"join control covers bottom stack",observer_geometry)
                assert observer_geometry["joinCompact"],(width,height,"observer join control too large",observer_geometry)
                assert observer_geometry["tableFillsObserver"],(width,height,"observer table leaves dead space",observer_geometry)
                page.screenshot(path=str(artifacts/f"{width}x{height}-observer-showdown.png"))
            # Native desktop/touch-sized button clicks with blank raise amount:
            for check in (False,True):
                s=state(check=check)
                page.evaluate("s=>JJ_TEST.setState(s)",s)
                page.evaluate("JJ_TEST.defer()")
                before=page.evaluate("JJ_TEST.sent.length")
                page.locator("#raiseTo").fill("")
                action="check" if check else "fold"
                page.locator(f'#actionBar [data-action="{action}"]').click()
                page.wait_for_function(f"JJ_TEST.sent.length==={before+1}")
                assert page.evaluate("JJ_TEST.sent.at(-1).body.action")==action
                assert page.evaluate("JJ_TEST.pending()")
                # WS can deliver another decision before the HTTP receipt arrives.
                newer=state(check=check)
                newer["hand"]["action_deadline"]=(datetime.now(timezone.utc)+timedelta(seconds=46)).isoformat()
                page.evaluate("s=>JJ_TEST.setState(s)",newer)
                assert page.locator(f'#actionBar [data-action="{action}"]').is_disabled()
                older=state(waiting=True)
                page.evaluate("s=>JJ_TEST.resolve(s)",older)
                page.wait_for_function("!JJ_TEST.pending()")
                assert page.evaluate("JJ_TEST.state().hand.action_deadline")==newer["hand"]["action_deadline"]
                assert page.locator(f'#actionBar [data-action="{action}"]').is_enabled(),"pending state stuck"
                # Failure also unlocks only after a successful fresh snapshot.
                page.evaluate("JJ_TEST.defer()")
                page.evaluate("s=>JJ_TEST.recoverWith(s)",newer)
                page.locator(f'#actionBar [data-action="{action}"]').click()
                page.wait_for_function(f"JJ_TEST.sent.length==={before+2}")
                page.evaluate("JJ_TEST.reject()")
                page.wait_for_function("!JJ_TEST.pending()")
                assert page.locator(f'#actionBar [data-action="{action}"]').is_enabled(),"failed action stuck"
            # Pre-action stays check/fold only and executes once when turn arrives.
            waiting=state(waiting=True)
            page.evaluate("s=>JJ_TEST.setState(s)",waiting)
            page.locator('[data-jj-preaction="check_fold"]').click()
            page.evaluate("JJ_TEST.defer()")
            before=page.evaluate("JJ_TEST.sent.length")
            next_turn=state(check=True)
            page.evaluate("s=>JJ_TEST.setState(s)",next_turn)
            page.wait_for_function(f"JJ_TEST.sent.length==={before+1}")
            assert page.evaluate("JJ_TEST.sent.at(-1).body.action")=="check"
            page.evaluate("s=>JJ_TEST.resolve(s)",waiting)
            page.wait_for_function("!JJ_TEST.pending()")
            assert page.evaluate("JJ_TEST.sent.length")==before+1
            # No action available while disconnected.
            page.evaluate("s=>JJ_TEST.setState(s)",state(check=True))
            page.evaluate("JJ_TEST.stale()")
            assert page.locator('[data-action="check"]').is_disabled()
            page.evaluate("s=>JJ_TEST.setState(s)",state(check=True))
            assert page.locator('[data-action="check"]').is_enabled()
            # Hand log remains live, is readable at scale, expands to a dedicated
            # surface, and the × control returns to the unchanged table.
            page.evaluate("s=>JJ_TEST.setState(s)",state(players=6))
            page.locator("#jjV7Menu summary").click()
            page.locator('[data-jj-mobile-side="log"]').click()
            assert page.locator("#pokerRoom .table-side").is_visible()
            assert "Player 2 raises to 4bb" in page.locator("#handLog").inner_text()
            log_font=page.evaluate("parseFloat(getComputedStyle(document.querySelector('#handLog>div')).fontSize)")
            if width<=760:
                assert log_font>=14,(width,height,"hand log text too small",log_font)
                assert page.evaluate("document.body.classList.contains('jj-v80-handlog-expanded')")
                full=page.evaluate("""() => {const r=document.querySelector('#pokerRoom .table-side').getBoundingClientRect();return r.left<=1&&r.top<=1&&r.right>=innerWidth-1&&r.bottom>=innerHeight-1}""")
                assert full,(width,height,"mobile hand log is not full screen")
            else:
                expand=page.locator('[data-jj-handlog-expand]')
                assert expand.is_visible()
                expand.click()
                assert page.evaluate("document.body.classList.contains('jj-v80-handlog-expanded')")
            close=page.locator("#jjV4SideClose")
            assert close.inner_text().strip()=="×"
            close.click()
            assert not page.locator("#pokerRoom .table-side").is_visible()
            assert not page.evaluate("document.body.classList.contains('jj-v80-handlog-expanded')")
            assert not errors, errors
            page.close()
        browser.close()
    print("JJ_SIMPLE_POKER_BROWSER_OK")

if __name__=="__main__":
    main()
