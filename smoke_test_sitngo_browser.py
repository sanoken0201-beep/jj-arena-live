"""Tournament UI uses ring actions at desktop and phone sizes."""
import shutil
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright
from served_assets import build_all
from poker_connection_fix import apply_to_build
from smoke_test_poker_simple import HOOKS, state


def main():
    with tempfile.TemporaryDirectory() as td, sync_playwright() as pw:
        root=Path(td);manifest=build_all(root);apply_to_build(root,manifest)
        js=(root/'static/app.js').read_text().replace('  init();','  bind();',1)
        end=js.rfind('})();')
        (root/'static/app.js').write_text(js[:end]+HOOKS+js[end:])
        html=(root/'index.html').read_text().replace('"/static/','"static/')
        (root/'index.html').write_text(html)
        chrome=next((shutil.which(x) for x in ('google-chrome','chromium','chromium-browser') if shutil.which(x)),None)
        browser=pw.chromium.launch(**({'executable_path':chrome} if chrome else {}),headless=True,args=['--no-sandbox','--allow-file-access-from-files'])
        for w,h in ((390,664),(360,640),(844,390),(1366,768)):
            page=browser.new_page(viewport={'width':w,'height':h})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto((root/'index.html').as_uri())
            page.wait_for_function('!!window.JJ_TEST')
            for check in (True,False):
                s=state(check=check)
                s['tournament']={'event_id':'sng-test','level':1,'bb_ante':200,'remaining':2,'entrants':2,'status':'running','results':[],'ante_paid':200,'next_level_at':None}
                page.evaluate('(s)=>JJ_TEST.setState(s)',s)
                assert page.locator('#jjSngTableInfo').is_visible()
                assert page.locator('[data-table-presence]:visible,#rebuyBtn:visible,#leaveSeatBtn:visible,#jjObserverJoin:visible').count()==0
                action='check' if check else 'fold'
                page.evaluate('JJ_TEST.defer()')
                page.locator(f'[data-action="{action}"]').click()
                sent=page.evaluate('JJ_TEST.sent.at(-1)')
                assert sent['body']['action']==action and sent['body']['hand_id']==s['hand']['id'],sent
                page.evaluate('(s)=>JJ_TEST.resolve(s)',s)
                page.wait_for_function('!JJ_TEST.pending()')
                # Hero's two cards must remain visible above action buttons.
                cards=page.locator('.jj-v7-hand')
                assert cards.is_visible()
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            s['tournament'].update(status='finished',remaining=1,results=[{'user_id':1,'name':'Hero','place':1},{'user_id':2,'name':'Other','place':2}])
            s['status']='waiting';s['legal']={'can_act':False}
            page.evaluate('(s)=>JJ_TEST.setState(s)',s)
            assert page.locator('#actionBar').inner_text().find('大会終了')>=0
            assert page.locator('#actionBar [data-action]').count()==0
            assert not errors,errors
            artifacts=Path('test-artifacts/sitngo');artifacts.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(artifacts/f'finished-{w}x{h}.png'))
            page.close()
        browser.close()
    print('JJ_SITNGO_BROWSER_OK')


if __name__=='__main__':main()
