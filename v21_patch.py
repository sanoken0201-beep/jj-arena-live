from __future__ import annotations
from pathlib import Path


def apply(root: Path) -> None:
    p=root/'server.py'; s=p.read_text(encoding='utf-8'); s=s.replace('version="1.10.0"','version="1.11.0"').replace('"version":"1.10.0"','"version":"1.11.0"').replace('request.url.query == "v=20"','request.url.query == "v=21"'); p.write_text(s,encoding='utf-8')
    p=root/'static'/'index.html'; s=p.read_text(encoding='utf-8').replace('?v=20','?v=21'); p.write_text(s,encoding='utf-8')
    p=root/'static'/'app.js'; s=p.read_text(encoding='utf-8')
    s=s.replace("if(v){switchView(v);closeMobileMore();mobileScrollTop();return}","if(v){switchView(v);syncMobileNavigation();closeMobileMore();mobileScrollTop();return}")
    s=s.replace("if(b){switchView(b.dataset.moreView);closeMobileMore();mobileScrollTop()}","if(b){switchView(b.dataset.moreView);syncMobileNavigation();closeMobileMore();mobileScrollTop()}")
    s=s.replace("$$('#mobileDock [data-mobile-view]').forEach(b=>b.classList.toggle('active',b.dataset.mobileView===currentView));","$$('#mobileDock [data-mobile-view]').forEach(b=>{const on=b.dataset.mobileView===currentView;b.classList.toggle('active',on);b.toggleAttribute('aria-current',on)});")
    p.write_text(s,encoding='utf-8')
    p=root/'static'/'sw.js'; s=p.read_text(encoding='utf-8').replace('jj-arena-live-v10','jj-arena-live-v11'); p.write_text(s,encoding='utf-8')
