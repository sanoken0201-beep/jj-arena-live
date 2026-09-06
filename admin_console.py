from __future__ import annotations

import json, math, re, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT=Path(__file__).resolve().parent
STATIC_DIR=ROOT/"admin_static"

class AdminUserPatch(BaseModel):
    disabled: bool|None=None
    club_verified: bool|None=None
    ranking_name: str|None=Field(default=None,max_length=60)
    admin_note: str|None=Field(default=None,max_length=1000)

class AdminPointIn(BaseModel):
    user_id:int=Field(gt=0)
    direction:str=Field(min_length=3,max_length=20)
    amount:float=Field(gt=0)
    reason:str=Field(min_length=2,max_length=500)
    effective_at:str|None=Field(default=None,max_length=40)

class AdminPinReset(BaseModel):
    pin:str=Field(min_length=6,max_length=6)

class AdminSettingsPatch(BaseModel):
    online_points_per_bb:float|None=Field(default=None,gt=0,le=100)
    manual_adjustment_limit:float|None=Field(default=None,gt=0,le=1_000_000)

def _now(db):
    try:return db.utcnow()
    except Exception:return datetime.now(timezone.utc).isoformat()

def _cols(db,con,table):
    if getattr(db,"IS_POSTGRES",False):
        return {str(r["column_name"]) for r in con.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=?",(table,)).fetchall()}
    return {str(r["name"]) for r in con.execute(f"PRAGMA table_info({table})").fetchall()}

def _ensure_schema(db):
    idcol="BIGSERIAL PRIMARY KEY" if getattr(db,"IS_POSTGRES",False) else "INTEGER PRIMARY KEY AUTOINCREMENT"
    uid="BIGINT" if getattr(db,"IS_POSTGRES",False) else "INTEGER"
    with db.connect() as con:
        cols=_cols(db,con,"users")
        if "club_verified" not in cols:con.execute("ALTER TABLE users ADD COLUMN club_verified INTEGER NOT NULL DEFAULT 0")
        if "admin_note" not in cols:con.execute("ALTER TABLE users ADD COLUMN admin_note TEXT NOT NULL DEFAULT ''")
        con.execute(f"""CREATE TABLE IF NOT EXISTS point_ledger(
          id TEXT PRIMARY KEY,user_id {uid} NOT NULL REFERENCES users(id),amount REAL NOT NULL,
          kind TEXT NOT NULL,reason TEXT NOT NULL,effective_at TEXT NOT NULL,
          created_by {uid} NOT NULL REFERENCES users(id),created_at TEXT NOT NULL,
          reversal_of TEXT REFERENCES point_ledger(id))""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_point_ledger_user ON point_ledger(user_id,effective_at)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_point_ledger_effective ON point_ledger(effective_at)")
        con.execute(f"""CREATE TABLE IF NOT EXISTS admin_audit_log(
          id {idcol},actor_id {uid} REFERENCES users(id),action TEXT NOT NULL,
          target_user_id {uid} REFERENCES users(id),detail_json TEXT NOT NULL DEFAULT '{{}}',created_at TEXT NOT NULL)""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_admin_audit_created ON admin_audit_log(created_at)")
        con.execute(f"""CREATE TABLE IF NOT EXISTS app_settings(
          key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_by {uid} REFERENCES users(id),updated_at TEXT NOT NULL)""")
        admin=con.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
        if admin:con.execute("UPDATE users SET club_verified=1 WHERE id=?",(admin["id"],))
        defaults={"online_points_per_bb":str(getattr(db,"ONLINE_POINTS_PER_BB",3)),"manual_adjustment_limit":"100000"}
        for k,v in defaults.items():
            if not con.execute("SELECT 1 FROM app_settings WHERE key=?",(k,)).fetchone():
                con.execute("INSERT INTO app_settings(key,value,updated_by,updated_at) VALUES (?,?,?,?)",(k,v,admin["id"] if admin else None,_now(db)))

def _get(db,key,default):
    with db.connect() as con:r=con.execute("SELECT value FROM app_settings WHERE key=?",(key,)).fetchone()
    return str(r["value"]) if r else default

def _set(db,key,value,actor):
    with db.connect() as con:
        if con.execute("SELECT 1 FROM app_settings WHERE key=?",(key,)).fetchone():
            con.execute("UPDATE app_settings SET value=?,updated_by=?,updated_at=? WHERE key=?",(value,actor,_now(db),key))
        else:con.execute("INSERT INTO app_settings(key,value,updated_by,updated_at) VALUES (?,?,?,?)",(key,value,actor,_now(db)))

def _audit(db,actor,action,target=None,**detail):
    with db.connect() as con:con.execute("INSERT INTO admin_audit_log(actor_id,action,target_user_id,detail_json,created_at) VALUES (?,?,?,?,?)",(actor,action,target,json.dumps(detail,ensure_ascii=False,separators=(",",":")),_now(db)))

def _revoke(db,uid):
    if hasattr(db,"delete_user_sessions"):db.delete_user_sessions(uid)
    else:
        with db.connect() as con:con.execute("DELETE FROM sessions WHERE user_id=?",(uid,))

def _bounds(server,season):
    start=getattr(server,"FALL_SEASON_START","2026-09-01");end=getattr(server,"FALL_SEASON_END","2027-04-01")
    return (start,end) if season=="fall" else ("0000-01-01",start)

def _rankings(db,server,month=None,season="fall"):
    season=(season or "fall").strip().lower()
    if season not in {"fall","summer"}:raise HTTPException(400,"season must be fall or summer")
    months=getattr(server,"FALL_SEASON_MONTHS",{"2026-09","2026-10","2026-11","2026-12","2027-01","2027-02","2027-03"})
    if season=="fall" and month and month not in months:return []
    start,end=_bounds(server,season)
    cw="WHERE name!='運営調整' AND date>=? AND date<?";cp=[start,end]
    ow="WHERE COALESCE(h.voided,0)=0 AND h.played_at>=? AND h.played_at<?";op=[start,end]
    lw="WHERE l.effective_at>=? AND l.effective_at<?";lp=[start,end]
    if month:
        cw+=" AND substr(date,1,7)=?";cp.append(month);ow+=" AND r.month=?";op.append(month);lw+=" AND substr(l.effective_at,1,7)=?";lp.append(month)
    with db.connect() as con:
        club=con.execute(f"SELECT name,SUM(points) points,COUNT(*) games,MAX(points) best,SUM(CASE WHEN points>0 THEN 1 ELSE 0 END) wins FROM entries {cw} GROUP BY name",cp).fetchall()
        try:online=con.execute(f"SELECT r.ranking_name name,SUM(r.points) points,COUNT(*) games,MAX(r.points) best,SUM(CASE WHEN r.points>0 THEN 1 ELSE 0 END) wins FROM online_hand_results r JOIN online_hands h ON h.hand_id=r.hand_id {ow} GROUP BY r.ranking_name",op).fetchall()
        except Exception:online=[]
        adj=con.execute(f"SELECT COALESCE(NULLIF(u.ranking_name,''),u.name) name,SUM(l.amount) points,COUNT(*) transactions FROM point_ledger l JOIN users u ON u.id=l.user_id {lw} GROUP BY COALESCE(NULLIF(u.ranking_name,''),u.name)",lp).fetchall()
    merged={}
    def blank(name,best=0):return {"name":name,"club_points":0.0,"online_points":0.0,"admin_points":0.0,"games":0,"online_hands":0,"adjustments":0,"best":float(best or 0),"wins":0}
    for r in club:
        d=blank(str(r["name"]),r["best"]);d.update(club_points=float(r["points"] or 0),games=int(r["games"] or 0),wins=int(r["wins"] or 0));merged[d["name"]]=d
    for r in online:
        name=str(r["name"]);d=merged.setdefault(name,blank(name,r["best"]));d["online_points"]=float(r["points"] or 0);d["games"]+=int(r["games"] or 0);d["online_hands"]=int(r["games"] or 0);d["best"]=max(d["best"],float(r["best"] or 0));d["wins"]+=int(r["wins"] or 0)
    for r in adj:
        name=str(r["name"]);d=merged.setdefault(name,blank(name));d["admin_points"]=float(r["points"] or 0);d["adjustments"]=int(r["transactions"] or 0)
    rows=[]
    for d in merged.values():
        for k in ("club_points","online_points","admin_points"):d[k]=round(float(d[k]),2)
        d["points"]=round(d["club_points"]+d["online_points"]+d["admin_points"],2);rows.append(d)
    rows.sort(key=lambda x:(-x["points"],-x["best"],x["name"]))
    return [r|{"rank":i+1,"season":season} for i,r in enumerate(rows)]

def _effective(v,db):
    if not v:return _now(db)
    v=v.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?",v):raise HTTPException(400,"反映日時が不正です")
    return v

def _pt(v):
    if not math.isfinite(v):raise HTTPException(400,"ポイント数が不正です")
    return round(float(v),2)

def install_admin_console(app):
    if getattr(app.state,"jj_admin_console_installed",False):return
    app.state.jj_admin_console_installed=True
    import db,server
    _ensure_schema(db)
    try:db.ONLINE_POINTS_PER_BB=float(_get(db,"online_points_per_bb",str(getattr(db,"ONLINE_POINTS_PER_BB",3))))
    except Exception:pass

    def rankings(month:str|None=None,season:str="fall",user=Depends(server.current_user)):return _rankings(db,server,month,season)
    app.add_api_route("/api/rankings",rankings,methods=["GET"],name="rankings_with_admin_ledger")
    route=app.router.routes.pop();idx=next((i for i,r in enumerate(app.router.routes) if getattr(r,"path",None)=="/api/rankings"),0);app.router.routes.insert(idx,route)

    @app.get("/api/admin/console/overview")
    def overview(user=Depends(server.admin_user)):
        start,end=_bounds(server,"fall")
        with db.connect() as con:
            s=con.execute("SELECT COUNT(*) total,SUM(CASE WHEN COALESCE(disabled,0)=0 THEN 1 ELSE 0 END) active,SUM(CASE WHEN COALESCE(disabled,0)<>0 THEN 1 ELSE 0 END) disabled,SUM(CASE WHEN COALESCE(club_verified,0)<>0 THEN 1 ELSE 0 END) verified FROM users").fetchone()
            l=con.execute("SELECT COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) credited,COALESCE(SUM(CASE WHEN amount<0 THEN -amount ELSE 0 END),0) collected,COUNT(*) transactions FROM point_ledger WHERE effective_at>=? AND effective_at<?",(start,end)).fetchone()
            dup=con.execute("SELECT COALESCE(NULLIF(ranking_name,''),name) ranking_name,COUNT(*) n FROM users WHERE COALESCE(disabled,0)=0 GROUP BY COALESCE(NULLIF(ranking_name,''),name) HAVING COUNT(*)>1 ORDER BY n DESC,ranking_name LIMIT 20").fetchall()
            recent=con.execute("SELECT a.id,a.action,a.detail_json,a.created_at,u.name actor_name,t.name target_name FROM admin_audit_log a LEFT JOIN users u ON u.id=a.actor_id LEFT JOIN users t ON t.id=a.target_user_id ORDER BY a.id DESC LIMIT 8").fetchall()
        ranks=_rankings(db,server,season="fall")
        return {"accounts":{"total":int(s["total"] or 0),"active":int(s["active"] or 0),"disabled":int(s["disabled"] or 0),"verified":int(s["verified"] or 0)},"ledger":{"credited":round(float(l["credited"] or 0),2),"collected":round(float(l["collected"] or 0),2),"transactions":int(l["transactions"] or 0)},"season":{"start":start,"end_exclusive":end},"ranking_total":round(sum(float(r["points"]) for r in ranks),2),"duplicate_mappings":[dict(r) for r in dup],"recent_audit":[dict(r) for r in recent]}

    @app.get("/api/admin/console/users")
    def users(q:str="",include_disabled:bool=True,user=Depends(server.admin_user)):
        q=(q or "").strip().lower();ranks={r["name"]:r for r in _rankings(db,server,season="fall")}
        sql="""SELECT u.id,u.name,u.role,u.disabled,u.ranking_name,u.created_at,u.club_verified,u.admin_note,
          (SELECT COUNT(*) FROM sessions s WHERE s.user_id=u.id AND s.expires_at>?) active_sessions,
          (SELECT MAX(s.created_at) FROM sessions s WHERE s.user_id=u.id) last_login_at,
          (SELECT COUNT(*) FROM users d WHERE COALESCE(d.disabled,0)=0 AND COALESCE(NULLIF(d.ranking_name,''),d.name)=COALESCE(NULLIF(u.ranking_name,''),u.name)) mapping_count FROM users u"""
        params=[_now(db)];where=[]
        if q:where.append("(lower(u.name) LIKE ? OR lower(COALESCE(u.ranking_name,'')) LIKE ? OR CAST(u.id AS TEXT) LIKE ?)");n=f"%{q}%";params.extend([n,n,n])
        if not include_disabled:where.append("COALESCE(u.disabled,0)=0")
        if where:sql+=" WHERE "+" AND ".join(where)
        sql+=" ORDER BY u.role DESC,u.disabled ASC,u.name ASC"
        with db.connect() as con:rows=con.execute(sql,params).fetchall()
        out=[]
        for row in rows:
            d=dict(row);r=ranks.get(d.get("ranking_name") or d.get("name"),{});d.update(season_points=float(r.get("points",0) or 0),club_points=float(r.get("club_points",0) or 0),online_points=float(r.get("online_points",0) or 0),admin_points=float(r.get("admin_points",0) or 0),duplicate_mapping=int(d.get("mapping_count") or 0)>1);out.append(d)
        return out

    @app.patch("/api/admin/console/users/{uid}")
    def update_user(uid:int,p:AdminUserPatch,user=Depends(server.admin_user)):
        with db.connect() as con:
            row=con.execute("SELECT id,name,role,disabled,ranking_name,club_verified,admin_note FROM users WHERE id=?",(uid,)).fetchone()
            if not row:raise HTTPException(404,"user not found")
            before=dict(row)
            if before["role"]=="admin" and p.disabled is True:raise HTTPException(400,"管理者アカウントは利用停止にできません")
            sets=[];args=[]
            if p.disabled is not None:sets.append("disabled=?");args.append(1 if p.disabled else 0)
            if p.club_verified is not None:sets.append("club_verified=?");args.append(1 if p.club_verified else 0)
            if p.ranking_name is not None:
                rn=p.ranking_name.strip()
                if not rn:raise HTTPException(400,"ランキング名を空にはできません")
                sets.append("ranking_name=?");args.append(rn)
            if p.admin_note is not None:sets.append("admin_note=?");args.append(p.admin_note.strip())
            if sets:con.execute(f"UPDATE users SET {','.join(sets)} WHERE id=?",args+[uid])
            after=dict(con.execute("SELECT id,name,role,disabled,ranking_name,club_verified,admin_note FROM users WHERE id=?",(uid,)).fetchone())
        if p.disabled is True:_revoke(db,uid)
        _audit(db,int(user["id"]),"user.update",uid,before=before,after=after);return after

    @app.post("/api/admin/console/users/{uid}/revoke-sessions")
    def revoke_sessions(uid:int,user=Depends(server.admin_user)):
        if uid==int(user["id"]):raise HTTPException(400,"現在操作中の管理者セッションは失効できません")
        with db.connect() as con:
            if not con.execute("SELECT 1 FROM users WHERE id=?",(uid,)).fetchone():raise HTTPException(404,"user not found")
        _revoke(db,uid);_audit(db,int(user["id"]),"user.sessions_revoke",uid);return {"ok":True}

    @app.post("/api/admin/console/users/{uid}/reset-pin")
    def reset_pin(uid:int,p:AdminPinReset,user=Depends(server.admin_user)):
        pin=p.pin.strip()
        if not re.fullmatch(r"\d{6}",pin):raise HTTPException(400,"PINは6桁の数字です")
        with db.connect() as con:
            target=con.execute("SELECT id,role FROM users WHERE id=?",(uid,)).fetchone()
            if not target:raise HTTPException(404,"user not found")
            if target["role"]=="admin":raise HTTPException(400,"管理者PINは本人の設定から変更してください")
            con.execute("UPDATE users SET password_hash=? WHERE id=?",(db.hash_password(pin),uid))
        _revoke(db,uid);_audit(db,int(user["id"]),"user.pin_reset",uid);return {"ok":True}

    @app.get("/api/admin/console/points")
    def ledger(user_id:int|None=None,limit:int=200,user=Depends(server.admin_user)):
        limit=max(1,min(int(limit),500));params=[];where=""
        if user_id:where="WHERE l.user_id=?";params.append(user_id)
        params.append(limit)
        with db.connect() as con:rows=con.execute(f"""SELECT l.id,l.user_id,l.amount,l.kind,l.reason,l.effective_at,l.created_at,l.reversal_of,
          u.name user_name,COALESCE(NULLIF(u.ranking_name,''),u.name) ranking_name,a.name actor_name,
          CASE WHEN EXISTS(SELECT 1 FROM point_ledger rv WHERE rv.reversal_of=l.id) THEN 1 ELSE 0 END reversed
          FROM point_ledger l JOIN users u ON u.id=l.user_id LEFT JOIN users a ON a.id=l.created_by {where} ORDER BY l.created_at DESC LIMIT ?""",params).fetchall()
        return [dict(r) for r in rows]

    @app.post("/api/admin/console/points")
    def point(p:AdminPointIn,user=Depends(server.admin_user)):
        direction=p.direction.strip().lower()
        if direction not in {"credit","debit"}:raise HTTPException(400,"direction must be credit or debit")
        cap=float(_get(db,"manual_adjustment_limit","100000"));amount=_pt(p.amount)
        if amount<=0 or amount>cap:raise HTTPException(400,f"1回の操作は0より大きく{cap:g}pt以下にしてください")
        signed=amount if direction=="credit" else -amount;effective=_effective(p.effective_at,db)
        with db.connect() as con:
            if not con.execute("SELECT 1 FROM users WHERE id=?",(p.user_id,)).fetchone():raise HTTPException(404,"user not found")
            tx="pt-"+uuid.uuid4().hex;con.execute("INSERT INTO point_ledger(id,user_id,amount,kind,reason,effective_at,created_by,created_at,reversal_of) VALUES (?,?,?,?,?,?,?,?,NULL)",(tx,p.user_id,signed,"credit" if signed>0 else "collection",p.reason.strip(),effective,user["id"],_now(db)))
        _audit(db,int(user["id"]),"point.credit" if signed>0 else "point.collection",p.user_id,transaction_id=tx,amount=signed,reason=p.reason.strip(),effective_at=effective);return {"id":tx,"user_id":p.user_id,"amount":signed,"effective_at":effective}

    @app.post("/api/admin/console/points/{txid}/reverse")
    def reverse(txid:str,user=Depends(server.admin_user)):
        with db.connect() as con:
            o=con.execute("SELECT * FROM point_ledger WHERE id=?",(txid,)).fetchone()
            if not o:raise HTTPException(404,"transaction not found")
            if o["reversal_of"]:raise HTTPException(400,"取消取引は再取消できません")
            if con.execute("SELECT 1 FROM point_ledger WHERE reversal_of=?",(txid,)).fetchone():raise HTTPException(409,"すでに取消済みです")
            rid="pt-"+uuid.uuid4().hex;amount=-float(o["amount"]);con.execute("INSERT INTO point_ledger(id,user_id,amount,kind,reason,effective_at,created_by,created_at,reversal_of) VALUES (?,?,?,?,?,?,?,?,?)",(rid,o["user_id"],amount,"reversal",f"取消: {o['reason']}",o["effective_at"],user["id"],_now(db),txid))
        _audit(db,int(user["id"]),"point.reverse",int(o["user_id"]),transaction_id=rid,reversal_of=txid,amount=amount);return {"id":rid,"reversal_of":txid,"amount":amount}

    @app.get("/api/admin/console/settings")
    def settings(user=Depends(server.admin_user)):
        return {"online_points_per_bb":float(_get(db,"online_points_per_bb",str(getattr(db,"ONLINE_POINTS_PER_BB",3)))),"manual_adjustment_limit":float(_get(db,"manual_adjustment_limit","100000")),"season_start":getattr(server,"FALL_SEASON_START","2026-09-01"),"season_end_exclusive":getattr(server,"FALL_SEASON_END","2027-04-01")}

    @app.patch("/api/admin/console/settings")
    def update_settings(p:AdminSettingsPatch,user=Depends(server.admin_user)):
        changed={}
        if p.online_points_per_bb is not None:
            rate=_pt(p.online_points_per_bb);_set(db,"online_points_per_bb",str(rate),int(user["id"]));db.ONLINE_POINTS_PER_BB=rate;changed["online_points_per_bb"]=rate
        if p.manual_adjustment_limit is not None:
            cap=_pt(p.manual_adjustment_limit);_set(db,"manual_adjustment_limit",str(cap),int(user["id"]));changed["manual_adjustment_limit"]=cap
        if changed:_audit(db,int(user["id"]),"settings.update",None,changed=changed)
        return settings(user)

    @app.get("/api/admin/console/audit")
    def audit(limit:int=200,user=Depends(server.admin_user)):
        limit=max(1,min(int(limit),500))
        with db.connect() as con:rows=con.execute("SELECT a.id,a.action,a.target_user_id,a.detail_json,a.created_at,u.name actor_name,t.name target_name FROM admin_audit_log a LEFT JOIN users u ON u.id=a.actor_id LEFT JOIN users t ON t.id=a.target_user_id ORDER BY a.id DESC LIMIT ?",(limit,)).fetchall()
        return [dict(r) for r in rows]

    if STATIC_DIR.exists():app.mount("/admin-static",StaticFiles(directory=STATIC_DIR),name="admin-static")
    @app.get("/admin",include_in_schema=False)
    @app.get("/admin/",include_in_schema=False)
    def admin_page():return FileResponse(STATIC_DIR/"index.html")
