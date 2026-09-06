from __future__ import annotations
from pathlib import Path
import re


def apply(root: Path) -> None:
    _patch_db(root / 'db.py')
    _patch_server(root / 'server.py')
    _patch_index(root / 'static' / 'index.html')
    _patch_appjs(root / 'static' / 'app.js')
    _patch_styles(root / 'static' / 'styles.css')
    _patch_sw(root / 'static' / 'sw.js')


def _patch_db(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    if 'def ensure_profile_columns()' in s:
        return
    marker = 'def init_db():'
    if marker not in s:
        raise RuntimeError('v1.13 db init marker not found')
    helper = r'''PROFILE_COLUMNS = (
    ("profile_grade", "TEXT"),
    ("profile_faculty", "TEXT"),
    ("profile_department", "TEXT"),
    ("profile_hometown", "TEXT"),
    ("profile_hobbies", "TEXT"),
    ("profile_bio", "TEXT"),
    ("profile_avatar", "TEXT"),
    ("profile_visible", "INTEGER NOT NULL DEFAULT 1"),
    ("profile_updated_at", "TEXT"),
)


def ensure_profile_columns() -> None:
    """Add optional member-profile fields without changing existing auth semantics."""
    with connect() as con:
        if IS_POSTGRES:
            for col, typ in PROFILE_COLUMNS:
                con.execute(f'ALTER TABLE users ADD COLUMN IF NOT EXISTS "{col}" {typ}')
            con.execute("UPDATE users SET profile_visible=1 WHERE profile_visible IS NULL")
        else:
            cols = {str(r["name"]) for r in con.execute("PRAGMA table_info(users)").fetchall()}
            for col, typ in PROFILE_COLUMNS:
                if col not in cols:
                    con.execute(f'ALTER TABLE users ADD COLUMN "{col}" {typ}')
            con.execute("UPDATE users SET profile_visible=1 WHERE profile_visible IS NULL")


'''
    s = s.replace(marker, helper + marker, 1)
    p.write_text(s, encoding='utf-8')


def _patch_server(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    s = s.replace('version="1.12.0"', 'version="1.13.0"').replace('"version":"1.12.0"', '"version":"1.13.0"')
    # Earlier patch chains can leave the server version one minor behind; normalize the current release too.
    s = s.replace('version="1.11.0"', 'version="1.13.0"').replace('"version":"1.11.0"', '"version":"1.13.0"')
    s = s.replace('request.url.query == "v=22"', 'request.url.query == "v=23"')
    if '\nimport base64\n' not in s:
        anchor = 'import asyncio\n'
        if anchor in s:
            s = s.replace(anchor, anchor + 'import base64\n', 1)
        else:
            s = 'import base64\n' + s
    if 'db.ensure_profile_columns()' not in s:
        s = s.replace('db.init_db()\n', 'db.init_db()\ndb.ensure_profile_columns()\n', 1)

    if 'class ProfileIn(BaseModel):' not in s:
        marker = 'class PointEntry(BaseModel):'
        if marker not in s:
            raise RuntimeError('v1.13 ProfileIn insertion marker not found')
        model = '''class ProfileIn(BaseModel):\n    grade: str = Field(default="", max_length=20)\n    faculty: str = Field(default="", max_length=80)\n    department: str = Field(default="", max_length=80)\n    hometown: str = Field(default="", max_length=80)\n    hobbies: str = Field(default="", max_length=250)\n    bio: str = Field(default="", max_length=600)\n    avatar_data: str = Field(default="", max_length=150000)\n    visible: bool = True\n\n\n'''
        s = s.replace(marker, model + marker, 1)

    if '@app.get("/api/profile/me")' not in s:
        marker = '@app.get("/api/rankings")'
        if marker not in s:
            raise RuntimeError('v1.13 profile endpoint insertion marker not found')
        endpoints = r'''PROFILE_TEXT_LIMITS = {
    "grade": 20,
    "faculty": 80,
    "department": 80,
    "hometown": 80,
    "hobbies": 250,
    "bio": 600,
}


def _profile_text(value: str | None, key: str) -> str:
    value = (value or "").strip()
    if len(value) > PROFILE_TEXT_LIMITS[key]:
        raise HTTPException(400, f"{key} is too long")
    return value


def _validate_profile_avatar(value: str | None) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    m = re.fullmatch(r"data:image/(webp|jpeg|png);base64,([A-Za-z0-9+/=]+)", value)
    if not m:
        raise HTTPException(400, "アイコン画像の形式が不正です")
    try:
        raw = base64.b64decode(m.group(2), validate=True)
    except Exception:
        raise HTTPException(400, "アイコン画像を読み取れません")
    if len(raw) > 100 * 1024:
        raise HTTPException(400, "アイコン画像が大きすぎます")
    kind = m.group(1)
    valid = (
        (kind == "png" and raw.startswith(b"\x89PNG\r\n\x1a\n"))
        or (kind == "jpeg" and raw.startswith(b"\xff\xd8\xff"))
        or (kind == "webp" and len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP")
    )
    if not valid:
        raise HTTPException(400, "アイコン画像の内容と形式が一致しません")
    return value


def _profile_row(row, *, own: bool = False) -> dict[str, Any]:
    d = dict(row)
    visible = bool(int(d.get("profile_visible") if d.get("profile_visible") is not None else 1))
    base = {
        "id": int(d["id"]),
        "name": d.get("name") or "",
        "ranking_name": d.get("ranking_name") or d.get("name") or "",
        "role": d.get("role") or "member",
        "visible": visible,
    }
    if not (own or visible):
        return base | {"grade":"","faculty":"","department":"","hometown":"","hobbies":"","bio":"","avatar_data":"","updated_at":None}
    return base | {
        "grade": d.get("profile_grade") or "",
        "faculty": d.get("profile_faculty") or "",
        "department": d.get("profile_department") or "",
        "hometown": d.get("profile_hometown") or "",
        "hobbies": d.get("profile_hobbies") or "",
        "bio": d.get("profile_bio") or "",
        "avatar_data": d.get("profile_avatar") or "",
        "updated_at": d.get("profile_updated_at"),
    }


@app.get("/api/profile/me")
def my_profile(user=Depends(current_user)):
    with db.connect() as con:
        row = con.execute("""
            SELECT id,name,role,ranking_name,profile_grade,profile_faculty,profile_department,
                   profile_hometown,profile_hobbies,profile_bio,profile_avatar,profile_visible,profile_updated_at
            FROM users WHERE id=?
        """, (user["id"],)).fetchone()
    if not row:
        raise HTTPException(404, "user not found")
    return _profile_row(row, own=True)


@app.post("/api/profile/me")
def save_my_profile(payload: ProfileIn, user=Depends(current_user)):
    values = {
        "grade": _profile_text(payload.grade, "grade"),
        "faculty": _profile_text(payload.faculty, "faculty"),
        "department": _profile_text(payload.department, "department"),
        "hometown": _profile_text(payload.hometown, "hometown"),
        "hobbies": _profile_text(payload.hobbies, "hobbies"),
        "bio": _profile_text(payload.bio, "bio"),
        "avatar": _validate_profile_avatar(payload.avatar_data),
        "visible": 1 if payload.visible else 0,
        "updated": db.utcnow(),
    }
    with db.connect() as con:
        con.execute("""
            UPDATE users SET profile_grade=?,profile_faculty=?,profile_department=?,profile_hometown=?,
                profile_hobbies=?,profile_bio=?,profile_avatar=?,profile_visible=?,profile_updated_at=? WHERE id=?
        """, (values["grade"],values["faculty"],values["department"],values["hometown"],
              values["hobbies"],values["bio"],values["avatar"],values["visible"],values["updated"],user["id"]))
        row = con.execute("""
            SELECT id,name,role,ranking_name,profile_grade,profile_faculty,profile_department,
                   profile_hometown,profile_hobbies,profile_bio,profile_avatar,profile_visible,profile_updated_at
            FROM users WHERE id=?
        """, (user["id"],)).fetchone()
    return _profile_row(row, own=True)


@app.get("/api/profiles")
def member_profiles(user=Depends(current_user)):
    with db.connect() as con:
        rows = con.execute("""
            SELECT id,name,role,ranking_name,profile_grade,profile_faculty,profile_department,
                   profile_hometown,profile_hobbies,profile_bio,profile_avatar,profile_visible,profile_updated_at
            FROM users WHERE COALESCE(disabled,0)=0
            ORDER BY CASE WHEN role='admin' THEN 0 ELSE 1 END, name ASC, id ASC
        """).fetchall()
    return [_profile_row(row, own=(int(row["id"]) == int(user["id"]))) for row in rows]


'''
        s = s.replace(marker, endpoints + marker, 1)
    p.write_text(s, encoding='utf-8')


def _patch_index(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    s = s.replace('?v=22', '?v=23')
    s = s.replace('?v=21', '?v=23')
    p.write_text(s, encoding='utf-8')


def _patch_appjs(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    if 'v1.13 optional member profiles' in s:
        return
    marker = '})();'
    pos = s.rfind(marker)
    if pos < 0:
        raise RuntimeError('v1.13 app.js closing marker not found')
    addon = r'''

  // v1.13 optional member profiles. Everything is voluntary and member-only.
  let profileDraftAvatar='';
  const profileInitials=name=>(String(name||'?').trim().slice(0,2)||'?');
  function profileAvatarHtml(p,cls='profile-avatar'){
    return p?.avatar_data?`<img class="${cls}" src="${safe(p.avatar_data)}" alt="${safe(p.name||'プロフィール')}のアイコン">`:`<div class="${cls} profile-avatar-fallback">${safe(profileInitials(p?.name))}</div>`;
  }
  function profileMeta(p){
    const school=[p.grade,p.faculty,p.department].filter(Boolean).join(' · '),items=[];
    if(school)items.push(`<span>🎓 ${safe(school)}</span>`);if(p.hometown)items.push(`<span>⌂ ${safe(p.hometown)}</span>`);if(p.hobbies)items.push(`<span>♧ ${safe(p.hobbies)}</span>`);
    return items.join('');
  }
  async function profileImageData(file){
    if(!file)return '';
    if(!/^image\/(jpeg|png|webp)$/.test(file.type))throw new Error('JPEG / PNG / WebP画像を選んでください');
    if(file.size>8*1024*1024)throw new Error('元画像は8MB以下にしてください');
    const url=URL.createObjectURL(file);
    try{
      const img=await new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>resolve(i);i.onerror=()=>reject(new Error('画像を読み込めません'));i.src=url});
      const size=160,canvas=document.createElement('canvas');canvas.width=size;canvas.height=size;const ctx=canvas.getContext('2d',{alpha:false});
      const scale=Math.max(size/img.naturalWidth,size/img.naturalHeight),w=img.naturalWidth*scale,h=img.naturalHeight*scale;
      ctx.fillStyle='#f4f7f5';ctx.fillRect(0,0,size,size);ctx.drawImage(img,(size-w)/2,(size-h)/2,w,h);
      let data=canvas.toDataURL('image/webp',.78);if(!data.startsWith('data:image/webp'))data=canvas.toDataURL('image/jpeg',.78);
      if(data.length>145000){data=canvas.toDataURL('image/jpeg',.62)}
      if(data.length>145000)throw new Error('画像を十分に圧縮できません。別の画像を選んでください');
      return data;
    }finally{URL.revokeObjectURL(url)}
  }
  function profileSettingsHtml(p){
    profileDraftAvatar=p.avatar_data||'';
    return `<div class="profile-settings-shell"><div class="profile-settings-head">${profileAvatarHtml(p,'profile-avatar profile-avatar-xl')}<div><div class="eyebrow">MEMBER PROFILE</div><h3>アカウント設定</h3><p class="hint">プロフィールはすべて任意です。ログイン済みのJJメンバーにだけ公開されます。</p></div></div>
      <form id="profileForm" class="profile-form stack">
        <div class="profile-avatar-actions"><label class="soft profile-upload">アイコンを選ぶ<input id="profileAvatarInput" type="file" accept="image/jpeg,image/png,image/webp" hidden></label><button type="button" class="ghost" id="profileAvatarRemove">アイコンを削除</button></div>
        <div class="profile-school-grid"><label>学年<input name="grade" maxlength="20" value="${safe(p.grade||'')}" placeholder="例：3年"></label><label>学部<input name="faculty" maxlength="80" value="${safe(p.faculty||'')}" placeholder="例：文学部"></label><label>学科<input name="department" maxlength="80" value="${safe(p.department||'')}" placeholder="例：英米文学科"></label></div>
        <label>出身<input name="hometown" maxlength="80" value="${safe(p.hometown||'')}" placeholder="例：大阪 / 兵庫県"></label>
        <label>趣味<input name="hobbies" maxlength="250" value="${safe(p.hobbies||'')}" placeholder="ポーカー、映画、旅行 など"></label>
        <label>自己紹介<textarea name="bio" maxlength="600" rows="4" placeholder="自由に記入できます">${safe(p.bio||'')}</textarea></label>
        <label class="profile-visibility"><span><b>プロフィールをメンバーに公開</b><small>OFFの場合、名前以外のプロフィール詳細は表示されません。</small></span><input name="visible" type="checkbox" ${p.visible?'checked':''}></label>
        <button class="primary full">プロフィールを保存</button>
      </form>
      <div class="profile-settings-divider"></div>
      <div class="profile-settings-actions"><button class="soft" type="button" id="openMemberDirectory">メンバー一覧を見る</button><button class="ghost" type="button" id="openPinSettings">6桁PINを変更</button></div></div>`;
  }
  async function openProfileSettings(){
    try{const p=await api('/profile/me');openModal(profileSettingsHtml(p));setTimeout(()=>$('#profileAvatarInput')?.focus?.(),0)}catch(err){toast(err.message)}
  }
  async function openMemberDirectory(){
    try{const list=await api('/profiles');openModal(`<div class="member-directory-head"><div><div class="eyebrow">JJ MEMBERS</div><h3>メンバー</h3><p class="hint">プロフィール設定は任意です。非公開の人は詳細を表示しません。</p></div><button class="soft" type="button" id="editMyProfileFromDirectory">自分を編集</button></div><div class="profile-directory">${list.map(p=>`<article class="profile-card ${p.visible?'':'profile-private'}"><div class="profile-card-head">${profileAvatarHtml(p)}<div><strong>${safe(p.ranking_name||p.name)}</strong><small>${p.role==='admin'?'ADMIN':'MEMBER'}${p.visible?'':' · 非公開'}</small></div></div>${p.visible?`<div class="profile-card-meta">${profileMeta(p)}</div>${p.bio?`<p>${safe(p.bio)}</p>`:''}`:'<p class="hint">プロフィールは非公開です。</p>'}</article>`).join('')}</div>`)}catch(err){toast(err.message)}
  }
  function openPinSettings(){
    openModal(`<h3>6桁PINを変更</h3><p class="hint">ログインに使う暗証番号です。</p><form id="pinChangeForm" class="stack"><label>現在の6桁PIN<input name="current_pin" type="password" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" required></label><label>新しい6桁PIN<input name="new_pin" type="password" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" required></label><button class="primary">PINを変更</button></form>`);
  }
  function updateProfileAvatarPreview(){
    const old=$('.profile-settings-head .profile-avatar-xl');if(!old)return;
    const wrap=document.createElement('div');wrap.innerHTML=profileDraftAvatar?`<img class="profile-avatar profile-avatar-xl" src="${safe(profileDraftAvatar)}" alt="アイコンプレビュー">`:`<div class="profile-avatar profile-avatar-xl profile-avatar-fallback">${safe(profileInitials(me?.name))}</div>`;
    old.replaceWith(wrap.firstElementChild);
  }
  // Capture the existing account button before the legacy PIN-only modal handler runs.
  document.addEventListener('click',async e=>{
    if(e.target.closest('#accountBtn')){e.preventDefault();e.stopImmediatePropagation();return openProfileSettings()}
    if(e.target.closest('#openMemberDirectory')){e.preventDefault();return openMemberDirectory()}
    if(e.target.closest('#editMyProfileFromDirectory')){e.preventDefault();return openProfileSettings()}
    if(e.target.closest('#openPinSettings')){e.preventDefault();return openPinSettings()}
    if(e.target.closest('#profileAvatarRemove')){e.preventDefault();profileDraftAvatar='';return updateProfileAvatarPreview()}
  },true);
  document.addEventListener('change',async e=>{
    if(e.target.id!=='profileAvatarInput')return;
    try{profileDraftAvatar=await profileImageData(e.target.files?.[0]);updateProfileAvatarPreview();toast('アイコンを準備しました。保存すると反映されます')}catch(err){toast(err.message);e.target.value=''}
  },true);
  document.addEventListener('submit',async e=>{
    if(e.target.id!=='profileForm')return;e.preventDefault();e.stopImmediatePropagation();const fd=new FormData(e.target),btn=e.submitter;
    try{if(btn){btn.disabled=true;btn.textContent='保存中…'}const saved=await post('/profile/me',{grade:fd.get('grade')||'',faculty:fd.get('faculty')||'',department:fd.get('department')||'',hometown:fd.get('hometown')||'',hobbies:fd.get('hobbies')||'',bio:fd.get('bio')||'',avatar_data:profileDraftAvatar,visible:fd.get('visible')==='on'});closeModal();toast('プロフィールを保存しました')}
    catch(err){toast(err.message)}finally{if(btn){btn.disabled=false;btn.textContent='プロフィールを保存'}}
  },true);
'''
    s = s[:pos] + addon + s[pos:]
    p.write_text(s, encoding='utf-8')


def _patch_styles(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    if 'v1.13 optional member profiles' in s:
        return
    s += r'''

/* v1.13 optional member profiles */
.profile-settings-shell{width:min(720px,100%)}
.profile-settings-head{display:flex;align-items:center;gap:18px;margin-bottom:20px}.profile-settings-head h3{margin:.15rem 0 .25rem}
.profile-avatar{width:58px;height:58px;border-radius:50%;object-fit:cover;display:grid;place-items:center;flex:0 0 auto;background:linear-gradient(145deg,#e4f5ed,#f4eee0);border:2px solid rgba(255,255,255,.9);box-shadow:0 8px 22px rgba(28,51,42,.12);font-weight:900;color:var(--text,#17231e)}
.profile-avatar-xl{width:86px;height:86px;font-size:1.35rem}.profile-avatar-fallback{letter-spacing:.04em}
.profile-avatar-actions{display:flex;gap:10px;flex-wrap:wrap}.profile-upload{display:inline-flex;align-items:center;justify-content:center;cursor:pointer}
.profile-school-grid{display:grid;grid-template-columns:.65fr 1fr 1fr;gap:12px}.profile-form textarea{resize:vertical;min-height:110px}
.profile-visibility{display:flex!important;align-items:center;justify-content:space-between;gap:16px;padding:14px 15px;border:1px solid var(--line,#dfe8e2);border-radius:14px;background:rgba(250,252,251,.8)}
.profile-visibility span{display:flex;flex-direction:column;gap:3px}.profile-visibility small{color:var(--muted,#68756f);font-weight:500;line-height:1.4}.profile-visibility input{width:22px;height:22px;flex:0 0 auto}
.profile-settings-divider{height:1px;background:var(--line,#dfe8e2);margin:22px 0 14px}.profile-settings-actions{display:flex;gap:10px;flex-wrap:wrap}
.member-directory-head{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;margin-bottom:18px}.member-directory-head h3{margin:.15rem 0 .25rem}
.profile-directory{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;max-height:min(65vh,680px);overflow:auto;padding:2px}
.profile-card{padding:16px;border:1px solid var(--line,#dfe8e2);border-radius:17px;background:linear-gradient(145deg,#fff,#f8fbf9);min-width:0}.profile-card-head{display:flex;align-items:center;gap:12px}.profile-card-head>div:last-child{min-width:0}.profile-card-head strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.profile-card-head small{display:block;margin-top:3px;color:var(--muted,#68756f);font-size:.68rem;font-weight:800;letter-spacing:.08em}
.profile-card-meta{display:flex;flex-wrap:wrap;gap:6px 10px;margin-top:13px;font-size:.76rem;color:var(--muted,#68756f)}.profile-card p{margin:12px 0 0;font-size:.82rem;line-height:1.65;white-space:pre-wrap}.profile-private{background:#fafbfa}
@media(max-width:760px){.profile-settings-head{align-items:flex-start}.profile-avatar-xl{width:74px;height:74px}.profile-school-grid{grid-template-columns:1fr}.profile-directory{grid-template-columns:1fr;max-height:62vh}.member-directory-head{align-items:flex-start;flex-direction:column}.profile-settings-actions>*{flex:1}.profile-avatar-actions>*{flex:1}}
'''
    p.write_text(s, encoding='utf-8')


def _patch_sw(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    # Normalize whichever cache label the previous patch chain emitted.
    s = re.sub(r'jj-arena-live-v\d+', 'jj-arena-live-v13', s)
    s = s.replace('?v=22', '?v=23').replace('?v=21', '?v=23')
    p.write_text(s, encoding='utf-8')
