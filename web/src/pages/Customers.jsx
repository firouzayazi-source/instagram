import React, { useEffect, useState } from 'react'
import InboxChips from './InboxChips.jsx'
import { Msg } from './Ai.jsx'
import { api, fa, timeAgo } from '../api.js'

const KIND = { dm_in: ['مشتری', ''], dm_out: ['پیج', 'good'], comment: ['کامنت', 'muted'], handoff: ['ارجاع', 'warn'] }

function List() {
  const [q, setQ] = useState('')
  const [tag, setTag] = useState('')
  const [data, setData] = useState(null)
  useEffect(() => {
    const t = setTimeout(() => api.get(`/api/customers?q=${encodeURIComponent(q)}&tag=${encodeURIComponent(tag)}`).then(setData).catch(() => {}), 250)
    return () => clearTimeout(t)
  }, [q, tag])

  return (
    <>
      <div className="actions" style={{ marginBottom: 8 }}>
        <input type="text" style={{ flex: 1 }} placeholder="جست‌وجو: نام کاربری، نام، شماره، یادداشت…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {data && (
        <div className="chips">
          <button className={`chip ${tag === '' ? 'active' : ''}`} onClick={() => setTag('')}>همه</button>
          {data.tags.map((t) => <button key={t} className={`chip ${tag === t ? 'active' : ''}`} onClick={() => setTag(tag === t ? '' : t)}>{t}</button>)}
        </div>
      )}
      {data && !data.items.length && <div className="empty">پرونده‌ای پیدا نشد. با اولین کامنت یا دایرکت هر نفر خودکار ساخته می‌شود.</div>}
      <div className="list">
        {(data?.items || []).map((p) => (
          <a key={p.id} href={`#/customers/${p.id}`} className="item">
            <div className="row">
              <span className="who">{p.name || (p.username ? `@${p.username}` : p.user_id)} <span className="pill muted">اینستاگرام</span></span>
              <span className="when">{timeAgo(p.last_seen)}</span>
            </div>
            <div className="row" style={{ marginTop: 4 }}>
              <span>{p.tags.map((t) => <span key={t} className="pill warn" style={{ marginLeft: 4 }}>{t}</span>)}</span>
              <span className="muted">{fa(p.messages)} پیام · {fa(p.comments)} کامنت{p.phone ? ` · ${p.phone}` : ''}</span>
            </div>
          </a>
        ))}
      </div>
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
      <header className="topbar"><h1>صندوق</h1>{id && <a href="#/customers" className="btn sm">همه‌ی مشتری‌ها</a>}</header>
      <InboxChips cur="customers" />
      {id ? <Profile id={decodeURIComponent(id)} /> : <List />}
    </>
  )
}
