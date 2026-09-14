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
        "hand":{"id":"visibility-hand","phase":"preflop","action_seat":1 if waiting else 0,"action_deadline":(datetime.now(timezone.utc)+timedelta(seconds=45)).isoformat(),"board":[],"current_bet":100,"log":[]},
        "legal":{"can_act":not waiting,"can_check":check,"can_call":not check,"can_raise":not waiting,"can_all_in":not waiting,"call_amount":0 if check else 50,"min_raise_to":200,"max_raise_to":15000},"last_result":None}

def main():
    chrome = next((shutil.which(n) for n in ("google-chrome","google-chrome-stable","chromium","chromium-browser") if shutil.which(n)),None)
    assert chrome, "Chrome is required"
    artifacts=ROOT/"test-artifacts"/"poker-simple"
    artifacts.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as td, sync_playwright() as p:
        root=Path(td)
        build_all(root)
        js=(root/"static/app.js").read_text()
        assert js.count("  init();")==1
        js=js.replace("  init();","  bind();",1)
        end=js.rfind("})();")
        js=js[:end]+HOOKS+js[end:]
        (root/"static/app.js").write_text(js)
        html=(root/"index.html").read_text().replace('"/static/','"static/')
        (root/"index.html").write_text(html)
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
                    page.screenshot(path=str(artifacts/f"{width}x{height}-{players}-{'wait' if waiting else 'act'}.png"))
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
            # Utilities are discoverable, and closing the drawer restores hit testing.
            page.locator("#jjV7Menu summary").click()
            page.locator('[data-jj-mobile-side="log"]').click()
            assert page.locator("#pokerRoom .table-side").is_visible()
            page.locator("#jjV4SideClose").click()
            assert not page.locator("#pokerRoom .table-side").is_visible()
            assert not errors, errors
            page.close()
        browser.close()
    print("JJ_SIMPLE_POKER_BROWSER_OK")

if __name__=="__main__":
    main()
