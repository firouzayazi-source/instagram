import React, { useEffect, useState } from 'react'
import InboxChips from './InboxChips.jsx'
import { Msg } from './Ai.jsx'
import { api, fa, timeAgo } from '../api.js'

const KIND = { dm_in: ['مشتری', ''], dm_out: ['پیج', 'good'], comment: ['کامنت', 'muted'], handoff: ['ارجاع', 'warn'] }

const left = (sec) => sec > 3600 ? `${fa(Math.floor(sec / 3600))} ساعت` : `${fa(Math.max(1, Math.floor(sec / 60)))} دقیقه`

function BulkBar({ ids, onDone }) {
  const [action, setAction] = useState('message')
  const [value, setValue] = useState('')
  const [msg, setMsg] = useState(null)
  if (!ids.length) return null
  async function run() {
    setMsg(null)
    try {
      const r = await api.post('/api/customers/bulk', { ids, action, value })
      setMsg({ ok: true, text: action === 'message'
        ? `${fa(r.queued)} پیام در صف ارسال (با فاصله‌ی چند ثانیه)` + (r.window_closed ? ` · ${fa(r.window_closed)} نفر پنجره‌ی ۲۴ ساعته‌شان بسته است` : '')
        : `${fa(r.changed)} پرونده به‌روز شد` })
      setValue(''); onDone()
    } catch (ex) { setMsg({ ok: false, text: ex.message }) }
  }
  return (
    <section className="card bulkbar">
      <div className="row-between"><b>{fa(ids.length)} نفر انتخاب شده</b>
        <select value={action} onChange={(e) => setAction(e.target.value)} style={{ width: 'auto' }}>
          <option value="message">پیام پیگیری در دایرکت</option><option value="tag_add">افزودن برچسب</option><option value="tag_remove">برداشتن برچسب</option>
        </select>
      </div>
      {action === 'message'
        ? <textarea rows={2} value={value} placeholder="مثلاً: سلام، هنوز دنبال ۱۳ پرو هستید؟ امروز موجود داریم 🙏" onChange={(e) => setValue(e.target.value)} />
        : <input type="text" value={value} placeholder="برچسب" onChange={(e) => setValue(e.target.value)} />}
      {action === 'message' && <p className="hint muted">قانون اینستاگرام: فقط به کسانی می‌رسد که در ۲۴ ساعت گذشته پیام داده‌اند؛ بقیه خودکار کنار گذاشته می‌شوند.</p>}
      <Msg m={msg} />
      <button className="btn primary" disabled={!value.trim()} onClick={run}>اجرا</button>
    </section>
  )
}

function Row({ p, sel, onSel, extra }) {
  return (
    <div className="item selectable">
      <input type="checkbox" checked={sel} onChange={onSel} aria-label="انتخاب" />
      <a href={`#/customers/${p.id}`}>
        <div className="row">
          <span className="who">{p.name || (p.username ? `@${p.username}` : p.user_id)} <span className="pill muted">اینستاگرام</span>
            {p.window_left > 0 && <span className="pill good" title="هنوز می‌شود در دایرکت پیام داد">پنجره باز: {left(p.window_left)}</span>}</span>
          <span className="when">{timeAgo(p.last_seen)}</span>
        </div>
        <div className="row" style={{ marginTop: 4 }}>
          <span>{p.tags.map((t) => <span key={t} className="pill warn" style={{ marginLeft: 4 }}>{t}</span>)}</span>
          <span className="muted">{fa(p.messages)} پیام · {fa(p.comments)} کامنت{p.phone ? ` · ${p.phone}` : ''}</span>
        </div>
        {extra}
      </a>
    </div>
  )
}

function useSelection() {
  const [sel, setSel] = useState([])
  const toggle = (id) => setSel((s) => s.includes(id) ? s.filter((x) => x !== id) : [...s, id])
  return [sel, setSel, toggle]
}

const FILTERS = [
  ['window', [['', 'پنجره‌ی پیام: همه'], ['open', 'پنجره‌ی پیام باز'], ['closed', 'پنجره بسته']]],
  ['phone', [['', 'شماره: همه'], ['yes', 'شماره دارد'], ['no', 'بی‌شماره']]],
  ['ordered', [['', 'سفارش: همه'], ['yes', 'سفارش داده'], ['no', 'سفارش نداده']]],
  ['days', [['0', 'هر زمان'], ['1', '۲۴ ساعت اخیر'], ['7', '۷ روز اخیر'], ['30', '۳۰ روز اخیر']]],
]

function List() {
  const [q, setQ] = useState('')
  const [tag, setTag] = useState('')
  const [f, setF] = useState({ window: '', phone: '', ordered: '', days: '0' })
  const [data, setData] = useState(null)
  const [sel, setSel, toggle] = useSelection()
  const [tick, setTick] = useState(0)
  useEffect(() => {
    const qs = new URLSearchParams({ q, tag, ...f }).toString()
    const t = setTimeout(() => api.get(`/api/customers?${qs}`).then(setData).catch(() => {}), 250)
    return () => clearTimeout(t)
  }, [q, tag, f, tick])
  const items = data?.items || []

  return (
    <>
      <div className="actions" style={{ marginBottom: 8 }}>
        <input type="text" style={{ flex: 1 }} placeholder="جست‌وجو: نام کاربری، نام، شماره، یادداشت…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="actions" style={{ flexWrap: 'wrap', marginBottom: 8 }}>
        {FILTERS.map(([k, opts]) => (
          <select key={k} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} style={{ width: 'auto' }}>
            {opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        ))}
      </div>
      {data && (
        <div className="chips">
          <button className={`chip ${tag === '' ? 'active' : ''}`} onClick={() => setTag('')}>همه</button>
          {data.tags.map((t) => <button key={t} className={`chip ${tag === t ? 'active' : ''}`} onClick={() => setTag(tag === t ? '' : t)}>{t}</button>)}
        </div>
      )}
      {items.length > 0 && (
        <div className="row-between" style={{ marginBottom: 6 }}>
          <span className="muted">{fa(items.length)} نفر</span>
          <button className="btn sm" onClick={() => setSel(sel.length === items.length ? [] : items.map((p) => p.id))}>{sel.length === items.length ? 'برداشتن انتخاب' : 'انتخاب همه'}</button>
        </div>
      )}
      {data && !items.length && <div className="empty">پرونده‌ای پیدا نشد. با اولین کامنت یا دایرکت هر نفر خودکار ساخته می‌شود.</div>}
      <div className="list">
        {items.map((p) => <Row key={p.id} p={p} sel={sel.includes(p.id)} onSel={() => toggle(p.id)} />)}
      </div>
      <BulkBar ids={sel} onDone={() => { setSel([]); setTick(tick + 1) }} />
    </>
  )
}

function Lost() {
  const [days, setDays] = useState(14)
  const [idle, setIdle] = useState(3)
  const [items, setItems] = useState(null)
  const [sel, setSel, toggle] = useSelection()
  const [tick, setTick] = useState(0)
  useEffect(() => { api.get(`/api/reports/lost?days=${days}&idle_hours=${idle}`).then((r) => setItems(r.items)).catch(() => {}) }, [days, idle, tick])
  if (!items) return <div className="empty">در حال بارگذاری…</div>
  const open = items.filter((p) => p.window_left > 0)
  return (
    <>
      <section className="card">
        <p style={{ marginTop: 0 }}>کسانی که قیمت یا موجودی پرسیدند یا قصد خرید داشتند، سفارشی ثبت نکردند و دیگر پیام ندادند.</p>
        <div className="actions" style={{ flexWrap: 'wrap' }}>
          <select value={days} onChange={(e) => setDays(Number(e.target.value))} style={{ width: 'auto' }}>
            {[[3, '۳ روز اخیر'], [7, '۷ روز اخیر'], [14, '۱۴ روز اخیر'], [30, '۳۰ روز اخیر']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <select value={idle} onChange={(e) => setIdle(Number(e.target.value))} style={{ width: 'auto' }}>
            {[[1, 'ساکت بیش از ۱ ساعت'], [3, 'ساکت بیش از ۳ ساعت'], [12, 'ساکت بیش از ۱۲ ساعت'], [24, 'ساکت بیش از ۲۴ ساعت']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div className="tiles" style={{ marginTop: 8 }}>
          <div className="tile warn"><b>{fa(items.length)}</b><span>فرصت ازدست‌رفته</span></div>
          <div className="tile good"><b>{fa(open.length)}</b><span>هنوز می‌شود پیگیری کرد</span></div>
        </div>
        {open.length > 0 && <button className="btn sm" style={{ marginTop: 8 }} onClick={() => setSel(open.map((p) => p.id))}>انتخاب همه‌ی پنجره‌بازها</button>}
        <p className="hint muted">برای پنجره‌بسته‌ها اینستاگرام اجازه‌ی پیام نمی‌دهد؛ اگر شماره دارند تماس بگیرید.</p>
      </section>
      {!items.length && <div className="empty">فرصت ازدست‌رفته‌ای نیست 👌</div>}
      <div className="list">
        {items.map((p) => <Row key={p.id} p={p} sel={sel.includes(p.id)} onSel={() => toggle(p.id)}
          extra={p.asked && <div className="text muted" style={{ marginTop: 4 }}>❓ {p.asked}</div>} />)}
      </div>
      <BulkBar ids={sel} onDone={() => { setSel([]); setTick(tick + 1) }} />
    </>
  )
}

function Profile({ id }) {
  const [p, setP] = useState(null)
  const [tags, setTags] = useState([])
  const [msg, setMsg] = useState(null)
  const [newTag, setNewTag] = useState('')
  const load = () => api.get(`/api/customers/${id}`).then(setP).catch((e) => setMsg({ ok: false, text: e.status === 404 ? 'پرونده پیدا نشد' : e.message }))
  useEffect(() => { load(); api.get('/api/customers?q=__none__').then((r) => setTags(r.tags)).catch(() => {}) }, [id])
  if (!p) return msg ? <Msg m={msg} /> : <div className="empty">در حال بارگذاری…</div>
  const set = (patch) => setP({ ...p, ...patch })
  const toggleTag = (t) => set({ tags: p.tags.includes(t) ? p.tags.filter((x) => x !== t) : [...p.tags, t] })

  async function save(e) {
    e.preventDefault(); setMsg(null)
    try { setP(await api.put(`/api/customers/${id}`, { name: p.name, phone: p.phone, notes: p.notes, tags: p.tags })); setMsg({ ok: true, text: 'ذخیره شد ✅' }) }
    catch (ex) { setMsg({ ok: false, text: ex.message }) }
  }

  return (
    <>
      <form className="card" onSubmit={save}>
        <div className="row-between">
          <h2 style={{ margin: 0 }}>{p.username ? `@${p.username}` : p.user_id}</h2>
          <span className="actions">
            {p.blocked && <span className="pill bad">مسدود</span>}
            <a className="btn sm" href={`#/messages/${p.user_id}`}>گفتگو</a>
          </span>
        </div>
        <p className="muted">اولین پیام {timeAgo(p.first_seen)} · آخرین {timeAgo(p.last_seen)} · {fa(p.messages)} دایرکت · {fa(p.comments)} کامنت</p>
        <div className="grid2">
          <div className="field"><label>نام</label><input type="text" value={p.name} onChange={(e) => set({ name: e.target.value })} /></div>
          <div className="field"><label>شماره‌ی موبایل</label><input type="text" dir="ltr" inputMode="tel" value={p.phone} placeholder="09…" onChange={(e) => set({ phone: e.target.value })} /></div>
        </div>
        <div className="field">
          <label>برچسب‌ها</label>
          <div className="actions" style={{ flexWrap: 'wrap' }}>
            {[...new Set([...tags, ...p.tags])].map((t) => (
              <button type="button" key={t} className={`chip ${p.tags.includes(t) ? 'active' : ''}`} onClick={() => toggleTag(t)}>{t}</button>
            ))}
            <input type="text" style={{ width: 120 }} placeholder="برچسب تازه" value={newTag} onChange={(e) => setNewTag(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && newTag.trim()) { e.preventDefault(); set({ tags: [...p.tags, newTag.trim()] }); setNewTag('') } }} />
          </div>
          <p className="hint muted">«قصد خرید»، «اقساطی» و «شکایت» را مغز مرکزی خودکار می‌زند؛ شماره‌ای که مشتری خودش بنویسد هم خودکار ثبت می‌شود.</p>
        </div>
        <div className="field"><label>یادداشت</label><textarea rows={3} value={p.notes} onChange={(e) => set({ notes: e.target.value })} /></div>
        <Msg m={msg} />
        <button className="btn primary">ذخیره</button>
      </form>

      <section className="card">
        <h2>سابقه</h2>
        {!p.timeline.length && <p className="muted">هنوز چیزی ثبت نشده.</p>}
        <div className="list">
          {p.timeline.map((e, i) => {
            const [label, cls] = KIND[e.kind] || [e.kind, '']
            return (
              <div key={i} className="item" style={{ cursor: 'default' }}>
                <div className="row"><span className={`pill ${cls}`}>{label}</span><span className="when">{timeAgo(e.at)}</span></div>
                <div className="text" style={{ whiteSpace: 'pre-line' }}>{e.text}</div>
              </div>
            )
          })}
        </div>
      </section>
    </>
  )
}

export default function Customers({ id }) {
  return (
    <>
      <header className="topbar"><h1>صندوق</h1>{id && id !== 'lost' && <a href="#/customers" className="btn sm">همه‌ی مشتری‌ها</a>}</header>
      <InboxChips cur={id === 'lost' ? 'lost' : 'customers'} />
      {id === 'lost' ? <Lost /> : id ? <Profile id={decodeURIComponent(id)} /> : <List />}
    </>
  )
}
