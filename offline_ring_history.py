"""Read-only offline ring input history, separate from ranking calculations."""

MARKER = "JJ_OFFLINE_RING_HISTORY_V1"


def history(db, *, start=None, end=None, player="", initial=None,
            date_from=None, date_to=None, offset=0, limit=40, admin=False):
    where = ["e.game_type='ring'", "e.name<>'運営調整'"]
    params = []
    for clause, value in (("e.date>=?", start), ("e.date<?", end),
                          ("e.date>=?", date_from),
                          ("SUBSTR(e.date,1,10)<=?", date_to),
                          ("e.initial=?", initial)):
        if value is not None:
            where.append(clause)
            params.append(value)
    if player.strip():
        where.append("LOWER(e.name) LIKE LOWER(?) ESCAPE '!'")
        value = player.strip().replace("!", "!!").replace("%", "!%").replace("_", "!_")
        params.append("%" + value + "%")
    # Do not expose account IDs or login names to ordinary members.
    actor = ", u.name AS entered_by" if admin else ""
    join = " LEFT JOIN users u ON u.id=e.created_by" if admin else ""
    with db.connect() as con:
        rows = con.execute(
            "SELECT e.id,e.name,e.date,e.game,e.initial,e.reentries,"
            "e.remaining,e.points,e.created_at" + actor +
            " FROM entries e" + join + " WHERE " + " AND ".join(where) +
            " ORDER BY e.date DESC,e.created_at DESC,e.id DESC LIMIT ? OFFSET ?",
            (*params, limit + 1, offset),
        ).fetchall()
    return {
        "entries": [dict(row) for row in rows[:limit]],
        "next_offset": offset + limit if len(rows) > limit else None,
    }


def install(app, server, db):
    from datetime import date
    from fastapi import Depends, HTTPException, Query
    import season_management

    @app.get("/api/points/ring-history")
    def ring_history(
        player: str = Query(default="", max_length=60),
        initial: int | None = Query(default=None, gt=0),
        date_from: date | None = None,
        date_to: date | None = None,
        archive: bool = False,
        offset: int = Query(default=0, ge=0, le=100000),
        limit: int = Query(default=40, ge=1, le=100),
        user=Depends(server.current_user),
    ):
        admin = user["role"] == "admin"
        if archive and not admin:
            raise HTTPException(403, "admin only")
        if date_from and date_to and date_from > date_to:
            raise HTTPException(400, "開始日は終了日以前にしてください")
        start, end = (None, None) if archive else season_management.bounds(db, "fall")
        return history(db, start=start, end=end, player=player, initial=initial,
                       date_from=date_from.isoformat() if date_from else None,
                       date_to=date_to.isoformat() if date_to else None,
                       offset=offset, limit=limit, admin=admin)


CLIENT = r"""
  // JJ_OFFLINE_RING_HISTORY_V1: load on demand, no polling or write-side changes.
  function jjInitRingHistory(){
    const recent=$('#recentEntries');
    if(!recent||!me)return;
    const identity=String(me.id)+':'+String(me.role);
    const existing=$('#jjRingHistory');
    if(existing?.dataset.identity===identity)return;
    existing?.remove();
    const panel=document.createElement('details');
    panel.id='jjRingHistory';panel.dataset.identity=identity;
    panel.style.marginTop='16px';
    panel.innerHTML='<summary>通常リングの入力履歴</summary><form class="form-grid" style="margin-top:12px"><label>プレイヤー名<input name="player" maxlength="60" placeholder="名前で検索"></label><label>ゲーム<select name="initial"><option value="">すべて</option><option value="450">1-3-3 / 450</option><option value="900">2-5-5 / 900（旧）</option><option value="1000">2-5 / 1000</option><option value="2000">5-10-10 / 2000（旧）</option><option value="3000">5-10 / 3000</option></select></label><label>開始日<input name="date_from" type="date"></label><label>終了日<input name="date_to" type="date"></label>'+(me.role==='admin'?'<label>対象期間<select name="archive"><option value="false">現在のシーズン</option><option value="true">全期間（過去の記録含む）</option></select></label>':'')+'<button type="submit" class="soft full">検索</button></form><p class="hint">登録済みの通常リング収支。ランキングの再計算は行いません。</p><div class="hint" role="status" aria-live="polite"></div><div class="list"></div><button type="button" class="soft full" hidden>さらに表示</button>';
    recent.after(panel);
    const form=panel.querySelector('form'),status=panel.querySelector('[role=status]'),list=panel.querySelector('.list'),more=panel.querySelector('button[hidden]');
    let sequence=0,next=null,filters=null,loaded=false;
    function current(){return panel.isConnected&&me&&identity===String(me.id)+':'+String(me.role)}
    function row(e){
      const el=document.createElement('div');el.className='list-item';
      const signed=(Number(e.points)>=0?'+':'')+fmt(e.points)+' pt';
      const date=String(e.date||'').replace('T',' ').slice(0,16);
      const entered=e.entered_by?' · 入力者 '+e.entered_by:'';
      const game=e.game||('初期点 '+fmt(e.initial));
      el.innerHTML='<strong>'+safe(e.name)+' <span style="color:'+(Number(e.points)>=0?'var(--accent2)':'var(--danger)')+'">'+safe(signed)+'</span></strong><div class="hint">'+safe(date+' · '+game)+'</div><div class="hint">'+safe('残り '+fmt(e.remaining)+' · リエントリー '+fmt(e.reentries)+entered)+'</div>';
      return el;
    }
    async function load(reset){
      if(!current())return;
      if(reset){filters=new URLSearchParams(new FormData(form));for(const [key,val] of [...filters])if(!val)filters.delete(key);next=0;list.replaceChildren()}
      if(next===null||!filters)return;
      const ticket=++sequence,query=new URLSearchParams(filters);
      query.set('offset',String(next));query.set('limit','40');
      status.textContent='読み込み中…';more.hidden=true;more.disabled=true;
      try{
        const data=await api('/points/ring-history?'+query.toString());
        if(ticket!==sequence||!current())return;
        if(!Array.isArray(data.entries))throw new Error('invalid history');
        list.append(...data.entries.map(row));
        next=data.next_offset;
        status.textContent=list.children.length?list.children.length+'件表示':'該当する記録はありません';
        more.hidden=next===null;more.disabled=false;
      }catch(error){
        if(ticket!==sequence||!current())return;
        status.textContent='履歴を取得できませんでした。再検索してください。';
        more.disabled=false;
      }
    }
    form.addEventListener('submit',e=>{e.preventDefault();loaded=true;load(true)});
    more.addEventListener('click',()=>load(false));
    panel.addEventListener('toggle',()=>{if(panel.open){loaded=true;load(true)}});
    panel.jjRefreshRingHistory=()=>{if(panel.open&&loaded)load(true)};
  }
"""


def transform_app_js(js):
    anchor = "  async function renderPoints(){"
    if js.count(anchor) != 1:
        raise RuntimeError("offline ring history renderPoints anchor drift")
    # Re-render on the existing points refresh (including successful submissions).
    return js.replace(anchor, CLIENT + anchor +
                      "jjInitRingHistory();$('#jjRingHistory')?.jjRefreshRingHistory?.();", 1)
