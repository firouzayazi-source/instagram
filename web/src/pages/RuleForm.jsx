import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import Icon from '../icons.jsx'
import Sortable, { AutoText } from '../sortable.jsx'

const EMPTY = {
  name: '', enabled: true, priority: 100, channels: ['comment'], post_scope: 'all',
  triggers: [{ match: 'contains', value: '' }],
  actions: { comment_mode: 'dm', public_replies: [''], private_replies: [''], dm_replies: [''], quick_replies: [], buttons: [] },
  advanced: { require_follow: false, follow_prompt: '', once_per_user: true, cooldown_minutes: 0, active_hours: null, followup: null,
    pause_ai_minutes: 0, handoff: false, max_uses: 0, over_limit_reply: '' },
}
const WHERE = [
  ['comment', 'کامنت پست و ریلز', 'کامنت زیر پست‌ها و ریلزها', 'comment'],
  ['dm', 'دایرکت', 'پیام‌های خصوصی کاربر', 'dm'],
  ['story_reply', 'جواب به استوری', 'وقتی کسی روی استوری جواب می‌دهد', 'story'],
  ['mention', 'منشن در استوری', 'وقتی کسی پیج را در استوری‌اش منشن می‌کند', 'at'],
]
// نوع جواب به کامنت؛ «هر دو» یعنی اول دایرکت، بعد جواب کوتاه زیر کامنت
const CMODES = [
  ['public', 'فقط جواب زیر کامنت', 'جواب عمومی، بدون دایرکت', 'comment'],
  ['dm', 'فقط دایرکت به کامنت‌گذار', 'متن کامل در دایرکت او (اینستاگرام فقط یک بار و تا ۷ روز اجازه می‌دهد)', 'dm'],
  ['both', 'دایرکت و جواب زیر کامنت', 'متن کامل در دایرکت، و یک جواب کوتاه زیر کامنت (مثلاً «دایرکت رو ببین»)', 'repeat'],
]
// عدد از کادر متن (رقم فارسی هم)؛ خالی یعنی ۰
const toNum = (v) => parseInt(String(v ?? '').replace(/[۰-۹]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d)), 10) || 0
const isOn = (v) => v !== 0 && v !== undefined && v !== null && v !== false   // '' یعنی روشن و هنوز در حال نوشتن
const modeOf = (a) => a.comment_mode || ((a.private_replies || []).some((t) => t.trim())
  ? ((a.public_replies || []).some((t) => t.trim()) ? 'both' : 'dm')
  : ((a.public_replies || []).some((t) => t.trim()) ? 'public' : 'dm'))
const MATCH = [['contains', 'شامل باشد'], ['exact', 'برابر دقیق'], ['starts_with', 'با این شروع شود'], ['any', 'هر مقداری'], ['regex', 'الگو (پیشرفته)']]
const faDate = (ts) => new Date(ts).toLocaleString('fa-IR', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Tehran' })

function Sec({ icon, title, desc, badge, children, open = true, onToggle }) {
  return (
    <section className="sec">
      <div className="sec-h" onClick={onToggle} style={onToggle ? { cursor: 'pointer' } : undefined}>
        <span className="ico"><Icon n={icon} /></span>
        <div className="grow"><h2>{title} {badge !== undefined && <span className="tag">{badge}</span>}</h2>{desc && <p>{desc}</p>}</div>
        {onToggle && <span className="iconbtn" style={{ transform: open ? 'rotate(90deg)' : 'rotate(-90deg)' }}><Icon n="chevL" /></span>}
      </div>
      {open && <div className="sec-b top">{children}</div>}
    </section>
  )
}

function Opt({ on, icon, title, desc, onClick }) {
  return (
    <button type="button" className={`opt ${on ? 'on' : ''}`} onClick={onClick} aria-pressed={on}>
      <span className="ico plain"><Icon n={icon} /></span>
      <span className="grow"><b>{title}</b><small>{desc}</small></span>
      <span className="tick">{on && <Icon n="check" />}</span>
    </button>
  )
}

function Adv({ on, icon, title, desc, onToggle, children, disabled }) {
  return (
    <div className={`adv ${on ? 'on' : ''}`} style={disabled ? { opacity: 0.5 } : undefined}>
      <div className="adv-h" onClick={disabled ? undefined : onToggle} role="checkbox" aria-checked={on}>
        <span className="ico plain"><Icon n={icon} /></span>
        <div className="grow"><b><span className="box">{on && <Icon n="check" />}</span>{title}</b><p>{desc}</p></div>
      </div>
      {on && children && <div className="adv-b">{children}</div>}
    </div>
  )
}

// پیام‌های شماره‌دار با جابه‌جایی؛ چند پیام یعنی هر بار یکی به نوبت (تا تکراری نباشد)
function Messages({ list, onChange, saved, placeholder, addLabel = 'پیام جدید', limit }) {
  const [pick, setPick] = useState(false)
  return (
    <>
      <Sortable items={list} onChange={onChange} renderItem={(t, i, handle) => (
        <div className="msg-row">
          {handle}
          <span className="num">{(i + 1).toLocaleString('fa-IR')}</span>
          <AutoText value={t} placeholder={placeholder} onChange={(e) => onChange(list.map((x, j) => (j === i ? e.target.value : x)))} />
          {limit && t.length > limit * 0.8 && <small className={t.length > limit ? 'err' : 'muted'} style={{ flex: 'none', fontSize: 11 }}>{t.length.toLocaleString('fa-IR')}/{limit.toLocaleString('fa-IR')}</small>}
          {list.length > 1 && <button type="button" className="x" aria-label="حذف" onClick={() => onChange(list.filter((_, j) => j !== i))}>✕</button>}
        </div>
      )} />
      {limit && list.some((t) => t.length > limit) && <div className="note warn">اینستاگرام دایرکت بلندتر از {limit.toLocaleString('fa-IR')} نویسه را نمی‌پذیرد. متن را کوتاه کنید، یا فهرست بلند (مثل لیست قیمت) را در سایت یا ربات بگذارید و با «دکمه‌ی لینک» بدهید.</div>}
      <div className="msg-add">
        <button type="button" className="btn sm" onClick={() => onChange([...list, ''])}><Icon n="plus" /> {addLabel}</button>
        {saved.length > 0 && <button type="button" className="btn sm" onClick={() => setPick(!pick)}><Icon n="msg" /> از پیام‌های قبلی</button>}
      </div>
      {pick && (
        <div className="list">
          {saved.map((s) => <button type="button" key={s} className="item" style={{ textAlign: 'right' }} onClick={() => { onChange([...list.filter((x) => x.trim()), s]); setPick(false) }}>{s.slice(0, 140)}</button>)}
        </div>
      )}
    </>
  )
}

// دکمه‌های لینک زیر دایرکت (تا ۳)؛ لینک‌ها هم مثل لینک‌های متن شمرده می‌شوند
function LinkButtons({ list, onChange }) {
  const set = (i, patch) => onChange(list.map((b, j) => (j === i ? { ...b, ...patch } : b)))
  return (
    <div className="sub-card">
      <b>دکمه‌ی لینک زیر دایرکت (اختیاری)</b>
      <small className="muted">به‌جای لینک خام در متن، دکمه‌ای که با یک لمس باز می‌شود؛ تا ۳ دکمه، عنوان تا ۲۰ نویسه.</small>
      {list.map((b, i) => (
        <div key={i} className="msg-row" style={{ flexWrap: 'wrap' }}>
          <input type="text" maxLength={20} value={b.title} placeholder="عنوان، مثلاً: 🌐 قیمت‌ها در سایت" style={{ flex: '1 1 40%', border: 0, background: 'transparent' }} onChange={(e) => set(i, { title: e.target.value })} />
          <input type="url" dir="ltr" value={b.url} placeholder="https://…" style={{ flex: '1 1 45%', border: 0, background: 'transparent' }} onChange={(e) => set(i, { url: e.target.value })} />
          <button type="button" className="x" aria-label="حذف" onClick={() => onChange(list.filter((_, j) => j !== i))}>✕</button>
        </div>
      ))}
      {list.length < 3 && <div className="msg-add"><button type="button" className="btn sm" onClick={() => onChange([...list, { title: '', url: '' }])}><Icon n="plus" /> دکمه‌ی لینک</button></div>}
    </div>
  )
}

function MediaGrid({ items, selected, onToggle }) {
  const [n, setN] = useState(6)
  if (!items.length) return <p className="muted">فهرست پست‌ها هنوز در دسترس نیست.</p>
  return (
    <>
      <div className="media-grid">
        {items.slice(0, n).map((m) => {
          const on = selected.includes(m.id)
          return (
            <button type="button" key={m.id} className={`media-card ${on ? 'on' : ''}`} onClick={() => onToggle(m.id)}>
              {on && <span className="sel">انتخاب‌شده</span>}
              {(m.thumbnail_url || m.media_url) ? <img src={m.thumbnail_url || m.media_url} alt="" loading="lazy" /> : <img alt="" />}
              <div className="cap">{(m.caption || m.product || m.note || '—').slice(0, 90)}</div>
              {m.timestamp && <div className="dt">{faDate(m.timestamp)}</div>}
            </button>
          )
        })}
      </div>
      {items.length > n && <button type="button" className="btn block" onClick={() => setN(n + 6)}>مشاهده‌ی بیشتر</button>}
    </>
  )
}

function Preview({ r, onClose }) {
  const first = (k) => (r.actions[k] || []).find((t) => t && t.trim())
  const ex = r.triggers.find((t) => t.value)?.value || 'سلام'
  const c = r.channels.includes('comment')
  return (
    <div className="overlay" onClick={onClose}>
      <div className="sheet" onClick={(e) => e.stopPropagation()}>
        <div className="row-between"><h2 style={{ margin: 0 }}>پیش‌نمایش</h2><button type="button" className="iconbtn" onClick={onClose} aria-label="بستن">✕</button></div>
        {c && <>
          <div className="bubble-label">زیر پست</div>
          <div className="bubble them">{ex}</div>
          {r.actions.comment_mode !== 'dm' && <div className="bubble us">{first('public_replies') || '— بدون جواب —'}</div>}
          {r.actions.comment_mode !== 'public' && <>
            <div className="bubble-label">در دایرکت کامنت‌گذار</div>
            <div className="bubble us">{first('private_replies') || '— بدون پیام —'}</div>
          </>}
        </>}
        {!c && <>
          <div className="bubble-label">دایرکت</div>
          <div className="bubble them">{ex}</div>
          <div className="bubble us">{first('dm_replies') || '— بدون پیام —'}</div>
          {(r.actions.quick_replies || []).filter(Boolean).length > 0 && (
            <div className="actions" style={{ marginTop: 6 }}>{r.actions.quick_replies.filter(Boolean).map((q) => <span key={q} className="chip">{q}</span>)}</div>
          )}
        </>}
        {r.advanced.followup?.text && <><div className="bubble-label">پیگیری بعد از {Math.round((r.advanced.followup.after_seconds || 0) / 60).toLocaleString('fa-IR')} دقیقه</div><div className="bubble us">{r.advanced.followup.text}</div></>}
      </div>
    </div>
  )
}

export default function RuleForm({ id }) {
  const isNew = id === 'new'
  const [r, setR] = useState(EMPTY)
  const [saved, setSaved] = useState([])
  const [media, setMedia] = useState([])
  const [stories, setStories] = useState([])
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [advOpen, setAdvOpen] = useState(false)
  const [preview, setPreview] = useState(false)
  const [formsList, setFormsList] = useState([])

  useEffect(() => {
    const pre = isNew && sessionStorage.getItem('rule_prefill')
    if (pre) {
      sessionStorage.removeItem('rule_prefill')
      try { const p = JSON.parse(pre); setR({ ...EMPTY, ...p, actions: { ...EMPTY.actions, ...(p.actions || {}) }, advanced: { ...EMPTY.advanced, ...(p.advanced || {}) } }) } catch { /* فرم خالی */ }
    }
    api.get('/api/saved-replies').then(setSaved).catch(() => {})
    api.get('/api/forms').then(setFormsList).catch(() => {})
    api.get('/api/media').then(setMedia).catch(() => {})
    api.get('/api/instagram/media-notes').then((d) => setStories(d.stories || [])).catch(() => {})
    if (!isNew) api.get('/api/rules').then((rs) => {
      const x = rs.find((y) => String(y.id) === id)
      if (x) {
        setR({
          ...x,
          actions: { comment_mode: modeOf(x.actions), public_replies: x.actions.public_replies?.length ? x.actions.public_replies : [''], private_replies: x.actions.private_replies?.length ? x.actions.private_replies : [''], dm_replies: x.actions.dm_replies || [], quick_replies: x.actions.quick_replies || [], form_id: x.actions.form_id || 0, buttons: x.actions.buttons || [] },
          // پیش‌فرض «یک بار برای هر کاربر» فقط برای دستور تازه است؛ دستور واردشده‌ای که این کلید را ندارد خاموش می‌ماند
          advanced: { ...EMPTY.advanced, once_per_user: false, ...x.advanced, cooldown_minutes: Math.round((x.advanced.cooldown_seconds || 0) / 60) },
        })
        setAdvOpen(true)
      }
    })
  }, [id])

  const set = (patch) => setR((x) => ({ ...x, ...patch }))
  const setAdv = (patch) => setR((x) => ({ ...x, advanced: { ...x.advanced, ...patch } }))
  const setAct = (k, list) => setR((x) => ({ ...x, actions: { ...x.actions, [k]: list } }))
  const hasC = r.channels.includes('comment')
  const hasD = ['dm', 'story_reply', 'mention'].some((c) => r.channels.includes(c))
  const scope = r.post_scope === 'all' ? null : r.post_scope
  const isNext = scope && scope.includes('next')
  const toggleChannel = (c) => set({
    channels: r.channels.includes(c) ? r.channels.filter((x) => x !== c) : [...r.channels, c],
    // پست‌های انتخاب‌شده برای کامنت با برداشتن «کامنت» نباید محدودیت استوری شوند (و برعکس)
    ...(c === 'comment' && r.post_scope !== 'all' ? { post_scope: 'all' } : {}),
  })
  const toggleScopeId = (mid) => set({ post_scope: scope.includes(mid) ? scope.filter((x) => x !== mid) : [...scope.filter((x) => x !== 'next'), mid] })
  const a = r.advanced
  const cmode = r.actions.comment_mode || 'dm'
  // دکمه‌ی لینک: زیر دایرکت به کامنت‌گذار (اگر دایرکت دارد) یا زیر جواب دایرکت؛ آنچه دیده نمی‌شود ذخیره هم نمی‌شود
  const btnInComment = hasC && cmode !== 'public'
  const btnVisible = btnInComment || hasD
  const formOk = cmode !== 'public' || hasD     // فرم در دایرکت ادامه پیدا می‌کند
  const advCount = [a.require_follow, scope && hasC, a.followup?.text !== undefined && a.followup !== null,
    isOn(a.max_uses), !!a.random_pick, !!r.actions.form_id, a.once_per_user, isOn(a.cooldown_minutes), !!a.active_hours, a.handoff, isOn(a.pause_ai_minutes)].filter(Boolean).length

  async function save(e) {
    e.preventDefault(); setErr('')
    if (!r.name.trim()) return setErr('یک نام برای دستور بنویسید')
    if (!r.channels.length) return setErr('محل دریافت پیام را انتخاب کنید')
    const has = (k) => (r.actions[k] || []).some((t) => t.trim())
    if (hasC && cmode !== 'public' && !has('private_replies')) return setErr('متن دایرکت به کامنت‌گذار را بنویسید')
    if (hasC && cmode !== 'dm' && !has('public_replies')) return setErr('متن جواب زیر کامنت را بنویسید')
    setBusy(true)
    const clean = (l) => (l || []).map((t) => t.trim()).filter(Boolean)
    const adv = { ...r.advanced }
    adv.cooldown_seconds = toNum(adv.cooldown_minutes) * 60
    delete adv.cooldown_minutes
    if (!adv.require_follow) delete adv.follow_prompt
    if (!adv.followup?.text) delete adv.followup
    if (!adv.active_hours) delete adv.active_hours
    adv.pause_ai_minutes = toNum(adv.pause_ai_minutes)
    if (!adv.pause_ai_minutes) delete adv.pause_ai_minutes
    if (!adv.handoff) delete adv.handoff
    if (!adv.random_pick) delete adv.random_pick
    if (adv.track_clicks !== false) delete adv.track_clicks
    adv.max_uses = toNum(adv.max_uses)
    if (!adv.max_uses) { delete adv.max_uses; delete adv.over_limit_reply }
    const body = {
      ...r, name: r.name.trim(), advanced: adv,
      post_scope: scope && scope.length ? scope : 'all',
      triggers: r.triggers.filter((t) => t.match === 'any' || t.value.trim()),
      actions: { ...(hasC ? { comment_mode: cmode } : {}),
        public_replies: hasC && cmode !== 'dm' ? clean(r.actions.public_replies) : [], private_replies: hasC && cmode !== 'public' ? clean(r.actions.private_replies) : [],
        dm_replies: hasD ? clean(r.actions.dm_replies) : [], quick_replies: hasD ? clean(r.actions.quick_replies).map((t) => t.slice(0, 20)).slice(0, 13) : [],
        ...(r.actions.form_id > 0 && formOk ? { form_id: Number(r.actions.form_id) } : {}),
        buttons: btnVisible ? (r.actions.buttons || []).map((b) => ({ title: b.title.trim(), url: b.url.trim() })).filter((b) => b.title || b.url) : [] },
    }
    if (!body.triggers.length) body.triggers = [{ match: 'any', value: '' }]
    delete body.id; delete body.use_count
    try {
      if (isNew) await api.post('/api/rules', body); else await api.put(`/api/rules/${id}`, body)
      location.hash = '#/rules'
    } catch (ex) { setErr(ex.message) }
    finally { setBusy(false) }
  }

  async function remove() {
    if (!confirm('این دستور حذف شود؟')) return
    await api.del(`/api/rules/${id}`); location.hash = '#/rules'
  }

  return (
    <form onSubmit={save}>
      <header className="topbar">
        <div className="title"><h1>پاسخ هوشمند</h1><span className="sub">{isNew ? 'ساخت پاسخ هوشمند' : 'ویرایش پاسخ هوشمند'}</span></div>
        <a href="#/rules" className="iconbtn" aria-label="بازگشت"><Icon n="back" /></a>
      </header>

      <Sec icon="target" title="شروع پاسخ هوشمند" desc="پاسخ هوشمند با یکی از شرط‌های زیر شروع می‌شود.">
        <div className="field" style={{ margin: 0 }}><label htmlFor="name">نام دستور</label>
          <input id="name" type="text" value={r.name} placeholder="مثلاً: قیمت ریلز اپ‌های ایرانی" onChange={(e) => set({ name: e.target.value })} /></div>
        <div className="sub-card">
          <b>محل دریافت پیام</b>
          {WHERE.map(([k, t, d, ic]) => <Opt key={k} on={r.channels.includes(k)} icon={ic} title={t} desc={d} onClick={() => toggleChannel(k)} />)}
        </div>
        <div className="sub-card">
          <b>عبارت شروع پاسخ</b>
          <small className="muted">متنی که با دریافت آن پاسخ هوشمند شروع می‌شود. اگر یکی از شرط‌ها درست باشد، اجرا می‌شود.</small>
          {r.triggers.map((t, i) => (
            <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {i > 0 && <div className="or">یا</div>}
              <select value={t.match} onChange={(e) => set({ triggers: r.triggers.map((x, j) => (j === i ? { ...x, match: e.target.value } : x)) })}>
                {MATCH.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
              {t.match === 'any'
                ? <div className="note info">هر پیامی این پاسخ هوشمند را فعال می‌کند.</div>
                : <div style={{ display: 'flex', gap: 8 }}>
                    <input type="text" value={t.value} placeholder="مثلاً قیمت" onChange={(e) => set({ triggers: r.triggers.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)) })} />
                    {r.triggers.length > 1 && <button type="button" className="iconbtn" aria-label="حذف شرط" onClick={() => set({ triggers: r.triggers.filter((_, j) => j !== i) })}><Icon n="trash" /></button>}
                  </div>}
            </div>
          ))}
          <button type="button" className="btn block" onClick={() => set({ triggers: [...r.triggers, { match: 'contains', value: '' }] })}><Icon n="plus" /> افزودن شرط بیشتر</button>
        </div>
      </Sec>

      {hasC && (
        <Sec icon="comment" title="جواب به کامنت" desc="کامنت چطور جواب بگیرد؟">
          {CMODES.map(([k, t, d, ic]) => <Opt key={k} on={cmode === k} icon={ic} title={t} desc={d} onClick={() => setAct('comment_mode', k)} />)}
          {cmode !== 'public' && (<>
            <div className="sub-card">
              <b>متن دایرکت به کامنت‌گذار <span className="tag">{r.actions.private_replies.filter((t) => t.trim()).length.toLocaleString('fa-IR')} پیام</span></b>
              {!r.actions.private_replies.some((t) => t.trim()) && <div className="note warn">متن دایرکت لازم است.</div>}
              <Messages limit={1000} list={r.actions.private_replies} onChange={(l) => setAct('private_replies', l)} saved={saved} placeholder="مثلاً: سلام! قیمت لحظه‌ای و اقساط اینجاست: https://t.me/…" />
              <small className="muted"><code dir="ltr">{'{username}'}</code> = نام کاربری مخاطب · <code dir="ltr">{'{bot}'}</code> = لینک ربات پشتیبان. هر لینک خودکار شمرده می‌شود (چند نفر زدند) و لینک ربات نشانه‌ی همین دستور را می‌گیرد.</small>
            </div>
            <LinkButtons list={r.actions.buttons || []} onChange={(l) => setAct('buttons', l)} />
          </>)}
          {cmode !== 'dm' && (
            <div className="sub-card">
              <b>جواب زیر کامنت <span className="tag">{r.actions.public_replies.filter((t) => t.trim()).length.toLocaleString('fa-IR')} متن</span></b>
              <small className="muted">{cmode === 'both' ? 'بعد از فرستادن دایرکت، یکی از این متن‌ها به نوبت زیر همان کامنت می‌رود.' : 'یکی از این متن‌ها به نوبت زیر کامنت جواب داده می‌شود؛ همه آن را می‌بینند.'}</small>
              {!r.actions.public_replies.some((t) => t.trim()) && <div className="note warn">متن جواب لازم است.</div>}
              <Messages list={r.actions.public_replies} onChange={(l) => setAct('public_replies', l)} saved={saved} placeholder={cmode === 'both' ? 'مثلاً: دایرکت رو ببین 📩' : 'مثلاً: ممنون از همراهیتون 🌸'} addLabel="متن جدید" />
            </div>
          )}
        </Sec>
      )}
      {hasD && (
        <Sec icon="dm" title={`جواب به ${r.channels.filter((c) => c !== 'comment').map((c) => ({ dm: 'دایرکت', story_reply: 'جواب استوری', mention: 'منشن' })[c]).join('، ')}`} badge={`${r.actions.dm_replies.filter((t) => t.trim()).length.toLocaleString('fa-IR')} پیام`}
          desc={hasC ? 'این متن فقط برای پیام‌هایی است که مستقیم در دایرکت می‌آیند، نه برای کامنت‌ها. چند پیام یعنی هر بار یکی به نوبت.' : 'چند پیام یعنی هر بار یکی به نوبت.'}>
          <Messages list={r.actions.dm_replies} onChange={(l) => setAct('dm_replies', l)} saved={saved} placeholder="متن پاسخ" />
          <small className="muted"><code dir="ltr">{'{username}'}</code> = نام کاربری مخاطب · <code dir="ltr">{'{bot}'}</code> = لینک ربات پشتیبان · هر لینک خودکار شمرده می‌شود.</small>
          {!btnInComment && <LinkButtons list={r.actions.buttons || []} onChange={(l) => setAct('buttons', l)} />}
          <div className="sub-card">
            <b>دکمه‌های پاسخ سریع (اختیاری)</b>
            <small className="muted">زیر پیام نشان داده می‌شوند؛ هر خط یک دکمه، تا ۱۳ دکمه و هر کدام ۲۰ نویسه.</small>
            <textarea rows={3} value={(r.actions.quick_replies || []).join('\n')} placeholder={'📄 شرایط اقساط\n🙋 صحبت با همکار'} onChange={(e) => setAct('quick_replies', e.target.value.split('\n'))} />
          </div>
        </Sec>
      )}

      <Sec icon="gear" title="تنظیمات پیشرفته" desc="شرط فالو، محدود به پست، فرم، پیگیری و…" badge={advCount ? `${advCount.toLocaleString('fa-IR')} فعال` : 'اختیاری'}
        open={advOpen} onToggle={() => setAdvOpen(!advOpen)}>
        <Adv on={!!a.require_follow} icon="insta" title="شرط دنبال کردن صفحه" desc="اگر کاربر صفحه را دنبال نکرده باشد، اول پیام راهنما دریافت می‌کند."
          onToggle={() => setAdv({ require_follow: !a.require_follow })}>
          <input type="text" value={a.follow_prompt || ''} placeholder="اول پیج رو فالو کن، بعد دوباره کامنت بذار 🙏" onChange={(e) => setAdv({ follow_prompt: e.target.value })} />
        </Adv>

        <Adv on={!!scope && hasC} disabled={!hasC} icon="target" title="محدود به پست" desc="برای کامنت‌ها: فقط روی پست یا ریل بعدی، یا پست‌های مشخص اجرا می‌شود."
          onToggle={() => set({ post_scope: scope ? 'all' : [] })}>
          <b>نوع اجرا</b>
          <Opt on={!!isNext} icon="sparkle" title="پست یا ریل بعدی" desc="اولین پستی که از این به بعد منتشر شود" onClick={() => set({ post_scope: ['next'] })} />
          <Opt on={!!scope && !isNext} icon="grid" title="انتخاب از پست‌های قبلی" desc="یک یا چند پست مشخص" onClick={() => set({ post_scope: (scope || []).filter((x) => x !== 'next') })} />
          {scope && !isNext && <><b>انتخاب پست</b><MediaGrid items={media} selected={scope} onToggle={toggleScopeId} /></>}
          {isNext && <div className="note info">به محض انتشار پست یا ریل بعدی، این دستور خودکار به آن وصل می‌شود.</div>}
        </Adv>

        {r.channels.includes('story_reply') && (
          <Adv on={!!scope && !hasC} disabled={hasC} icon="story" title="محدود به استوری" desc="فقط جواب‌های استوری‌های انتخاب‌شده (استوری‌های ۲۴ ساعت اخیر)."
            onToggle={() => set({ post_scope: scope ? 'all' : [] })}>
            <MediaGrid items={stories} selected={scope || []} onToggle={toggleScopeId} />
          </Adv>
        )}

        <Adv on={a.followup !== null && a.followup !== undefined} icon="bell" title="پیگیری خودکار" desc="بعد از زمان مشخص‌شده، پیام پیگیری در دایرکت فرستاده می‌شود (فقط تا ۲۴ ساعت بعد از پیام کاربر)."
          onToggle={() => setAdv({ followup: a.followup ? null : { after_seconds: 3600, text: '' } })}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}><span>بعد از</span>
            <input type="number" min="1" style={{ width: 110 }} value={a.followup ? Math.round(a.followup.after_seconds / 60) : ''} onChange={(e) => setAdv({ followup: { ...a.followup, after_seconds: Number(e.target.value) * 60 } })} /><span>دقیقه</span></div>
          <textarea value={a.followup?.text || ''} placeholder="متن پیگیری، مثلاً: سؤالی بود در خدمتم 🙏" onChange={(e) => setAdv({ followup: { ...a.followup, text: e.target.value } })} />
        </Adv>

        <Adv on={!!r.actions.form_id && formOk} disabled={!formOk} icon="edit" title="شروع فرم" desc="بعد از پیام این دستور، سؤال‌های فرم یکی‌یکی در دایرکت پرسیده و جواب‌ها ذخیره می‌شود (حتی وقتی جواب خودکار دایرکت خاموش است)."
          onToggle={() => setR((x) => ({ ...x, actions: { ...x.actions, form_id: x.actions.form_id ? 0 : (formsList[0]?.id || -1) } }))}>
          {formsList.length ? (
            <select value={r.actions.form_id > 0 ? r.actions.form_id : ''} onChange={(e) => setR((x) => ({ ...x, actions: { ...x.actions, form_id: Number(e.target.value) } }))}>
              <option value="" disabled>یک فرم انتخاب کنید</option>
              {formsList.map((f) => <option key={f.id} value={f.id}>{f.name}{f.enabled ? '' : ' (خاموش)'}</option>)}
            </select>
          ) : <div className="note warn">هنوز فرمی نساخته‌اید. <a href="#/smart/forms/new">ساخت فرم</a></div>}
          {hasC && <div className="note info">برای کامنت، سؤال اول همراه همان دایرکت به کامنت‌گذار می‌رود و جواب‌ها در دایرکت ادامه پیدا می‌کند.</div>}
        </Adv>

        <Adv on={a.track_clicks !== false} icon="link" title="شمارش کلیک لینک‌ها" desc="لینک‌های پیام و دکمه‌ها از نشانی کوتاه پنل رد می‌شوند تا معلوم شود چند نفر زدند (در فهرست دستورها). خاموش: لینک خام فرستاده می‌شود."
          onToggle={() => setAdv({ track_clicks: a.track_clicks === false })} />

        <Adv on={!!a.random_pick} icon="repeat" title="انتخاب تصادفی متن" desc="به‌جای به نوبت (۱، ۲، ۳…)، هر بار یکی از متن‌ها تصادفی فرستاده می‌شود؛ طبیعی‌تر دیده می‌شود."
          onToggle={() => setAdv({ random_pick: !a.random_pick })} />

        <Adv on={isOn(a.max_uses)} icon="clock" title="محدودیت تعداد پاسخ" desc="بعد از رسیدن به سقف، پاسخ اصلی متوقف می‌شود و پیام جایگزین فرستاده می‌شود (اگر بنویسید)."
          onToggle={() => setAdv({ max_uses: isOn(a.max_uses) ? 0 : 100 })}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}><span>سقف</span>
            <input type="text" inputMode="numeric" style={{ width: 120 }} value={a.max_uses || ''} onChange={(e) => setAdv({ max_uses: e.target.value })} /><span>پاسخ</span></div>
          <small className="muted">تا الان {(r.use_count || 0).toLocaleString('fa-IR')} بار اجرا شده.</small>
          <textarea value={a.over_limit_reply || ''} placeholder="پیام جایگزین (اختیاری)، مثلاً: ظرفیت این پیشنهاد تمام شد 🙏" onChange={(e) => setAdv({ over_limit_reply: e.target.value })} />
        </Adv>

        <Adv on={!!a.once_per_user} icon="user" title="هر کاربر فقط یک بار" desc="اگر کسی دوباره کامنت یا پیام بدهد، این دستور دوباره برایش اجرا نمی‌شود."
          onToggle={() => setAdv({ once_per_user: !a.once_per_user })} />

        <Adv on={isOn(a.cooldown_minutes)} icon="repeat" title="فاصله‌ی بین دو پاسخ به یک نفر" desc="پاسخ دوباره به همان نفر فقط بعد از این مدت."
          onToggle={() => setAdv({ cooldown_minutes: isOn(a.cooldown_minutes) ? 0 : 60 })}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}><input type="text" inputMode="numeric" style={{ width: 110 }} value={a.cooldown_minutes || ''} onChange={(e) => setAdv({ cooldown_minutes: e.target.value })} /><span>دقیقه</span></div>
        </Adv>

        <Adv on={!!a.active_hours} icon="cal" title="ساعت فعال" desc="فقط در این بازه‌ی ساعت اجرا شود (به وقت سرور)."
          onToggle={() => setAdv({ active_hours: a.active_hours ? null : [9, 23] })}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}><span>از</span>
            <input type="number" min="0" max="23" style={{ width: 80 }} value={a.active_hours?.[0] ?? ''} onChange={(e) => setAdv({ active_hours: [Number(e.target.value), a.active_hours?.[1] ?? 23] })} /><span>تا</span>
            <input type="number" min="0" max="24" style={{ width: 80 }} value={a.active_hours?.[1] ?? ''} onChange={(e) => setAdv({ active_hours: [a.active_hours?.[0] ?? 0, Number(e.target.value)] })} /></div>
        </Adv>

        <Adv on={!!a.handoff} icon="hand" title="سپردن به همکار" desc="بعد از اجرا، در «ارجاع‌ها» و گروه تلگرام به همکار خبر داده می‌شود."
          onToggle={() => setAdv({ handoff: !a.handoff })} />

        {hasD && (
          <Adv on={isOn(a.pause_ai_minutes)} icon="pause" title="توقف ربات برای همین مشتری" desc="تا این مدت ربات در دایرکت او ساکت می‌ماند تا همکار جواب بدهد."
            onToggle={() => setAdv({ pause_ai_minutes: isOn(a.pause_ai_minutes) ? 0 : 60 })}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}><input type="text" inputMode="numeric" style={{ width: 110 }} value={a.pause_ai_minutes || ''} onChange={(e) => setAdv({ pause_ai_minutes: e.target.value })} /><span>دقیقه</span></div>
          </Adv>
        )}

        <div className="field" style={{ margin: 0 }}><label>اولویت (عدد کوچک‌تر زودتر بررسی می‌شود)</label>
          <input type="number" value={r.priority} onChange={(e) => set({ priority: Number(e.target.value) })} /></div>
      </Sec>

      <Sec icon="save" title="ذخیره و فعال‌سازی" desc="بعد از ذخیره، پاسخ هوشمند با همین شرط‌ها و پیام‌ها فعال می‌شود.">
        {err && <div className="note warn">{err}</div>}
        <div style={{ display: 'flex', gap: 10 }}>
          <button className="btn primary big" style={{ flex: 1 }} disabled={busy}><Icon n="save" /> {busy ? '…' : isNew ? 'ایجاد' : 'ذخیره'}</button>
          <button type="button" className="btn big" style={{ flex: 1 }} onClick={() => setPreview(true)}><Icon n="eye" /> پیش‌نمایش</button>
        </div>
        {!isNew && <button type="button" className="btn danger block" onClick={remove}><Icon n="trash" /> حذف این دستور</button>}
      </Sec>
      {preview && <Preview r={r} onClose={() => setPreview(false)} />}
    </form>
  )
}
