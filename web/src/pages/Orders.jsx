import React, { useEffect, useState } from 'react'
import InboxChips from './InboxChips.jsx'
import { Msg } from './Ai.jsx'
import { api, fa, money, timeAgo } from '../api.js'

const CLS = { new: 'warn', awaiting_payment: 'warn', receipt: 'bad', confirmed: 'good', shipped: 'good', done: 'muted', canceled: 'muted' }

function List() {
  const [status, setStatus] = useState('')
  const [d, setD] = useState(null)
  useEffect(() => { api.get(`/api/orders?status=${status}`).then(setD).catch(() => {}) }, [status])
  if (!d) return <div className="empty">در حال بارگذاری…</div>
  return (
    <>
      <div className="chips">
        <button className={`chip ${status === '' ? 'active' : ''}`} onClick={() => setStatus('')}>همه</button>
        {Object.entries(d.statuses).map(([k, l]) => (
          <button key={k} className={`chip ${status === k ? 'active' : ''}`} onClick={() => setStatus(k)}>{l}{d.stats[k] ? ` (${fa(d.stats[k].count)})` : ''}</button>
        ))}
      </div>
      {!d.items.length && <div className="empty">سفارشی نیست. سفارش‌هایی که مشتری‌ها در دایرکت ثبت می‌کنند اینجا می‌آید (تنظیم در «کانال‌ها ← اینستاگرام ← فروش»).</div>}
      <div className="list">
        {d.items.map((o) => (
          <a key={o.id} href={`#/orders/${o.id}`} className="item">
            <div className="row"><span className="who">#{fa(o.id)} · {o.name} <span className={`pill ${CLS[o.status]}`}>{o.status_label}</span></span><span className="when">{timeAgo(o.created_at)}</span></div>
            <div className="row" style={{ marginTop: 4 }}><span>{o.product || '—'}</span><span className="muted">{o.price ? money(o.price) : ''} · {o.city}</span></div>
          </a>
        ))}
      </div>
    </>
  )
}

function Detail({ id }) {
  const [o, setO] = useState(null)
  const [msg, setMsg] = useState(null)
  useEffect(() => { api.get(`/api/orders/${id}`).then(setO).catch((e) => setMsg({ ok: false, text: e.message })) }, [id])
  if (!o) return msg ? <Msg m={msg} /> : <div className="empty">در حال بارگذاری…</div>
  const set = (patch) => setO({ ...o, ...patch })

  async function save(e) {
    e.preventDefault(); setMsg(null)
    try {
      const r = await api.put(`/api/orders/${id}`, { status: o.status, note: o.note, name: o.name, phone: o.phone, city: o.city, address: o.address, product: o.product, price: o.price || null })
      setO({ ...r, statuses: o.statuses }); setMsg({ ok: true, text: 'ذخیره شد ✅' })
    } catch (ex) { setMsg({ ok: false, text: ex.message }) }
  }

  return (
    <form className="card" onSubmit={save}>
      <div className="row-between">
        <h2 style={{ margin: 0 }}>سفارش #{fa(o.id)}</h2>
        <span className="actions">
          <a className="btn sm" href={`#/messages/${o.user_id}`}>گفتگو</a>
          <a className="btn sm" href={`#/customers/${o.channel}:${o.user_id}`}>پرونده</a>
        </span>
      </div>
      <p className="muted">{o.username ? `@${o.username} · ` : ''}ثبت {timeAgo(o.created_at)} · به‌روزرسانی {timeAgo(o.updated_at)}</p>
      <div className="field">
        <label>وضعیت</label>
        <select value={o.status} onChange={(e) => set({ status: e.target.value })}>
          {Object.entries(o.statuses).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <p className="hint muted">«ارسال شد» و «تحویل شد» برچسب «خرید کرده» را به پرونده‌ی مشتری می‌زند. هر تغییر وضعیت به وبهوک هم می‌رود.</p>
      </div>
      {o.receipt_url && (
        <div className="field">
          <label>رسید پرداخت</label>
          <a href={o.receipt_url} target="_blank" rel="noreferrer"><img src={o.receipt_url} alt="رسید" style={{ maxWidth: '100%', maxHeight: 360, borderRadius: 8 }} /></a>
          <p className="hint muted">لینک عکس‌های اینستاگرام بعد از مدتی باطل می‌شود؛ نسخه‌ی رسید در گروه تلگرام می‌ماند.</p>
        </div>
      )}
      <div className="grid2">
        <div className="field"><label>محصول</label><input type="text" value={o.product} onChange={(e) => set({ product: e.target.value })} /></div>
        <div className="field"><label>مبلغ (تومان)</label><input type="number" min="0" value={o.price || ''} onChange={(e) => set({ price: e.target.value ? Number(e.target.value) : null })} /></div>
        <div className="field"><label>نام</label><input type="text" value={o.name} onChange={(e) => set({ name: e.target.value })} /></div>
        <div className="field"><label>شماره</label><input type="text" dir="ltr" value={o.phone} onChange={(e) => set({ phone: e.target.value })} /></div>
        <div className="field"><label>شهر</label><input type="text" value={o.city} onChange={(e) => set({ city: e.target.value })} /></div>
      </div>
      <div className="field"><label>آدرس</label><textarea rows={2} value={o.address} onChange={(e) => set({ address: e.target.value })} /></div>
      <div className="field"><label>یادداشت داخلی</label><textarea rows={2} value={o.note} placeholder="مثلاً کد رهگیری پست" onChange={(e) => set({ note: e.target.value })} /></div>
      <Msg m={msg} />
      <button className="btn primary">ذخیره</button>
    </form>
  )
}

export default function Orders({ id }) {
  return (
    <>
      <header className="topbar"><h1>صندوق</h1>{id && <a href="#/orders" className="btn sm">همه‌ی سفارش‌ها</a>}</header>
      <InboxChips cur="orders" />
      {id ? <Detail id={id} /> : <List />}
    </>
  )
}
