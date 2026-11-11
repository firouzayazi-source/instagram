import React, { useEffect, useState } from 'react'
import Icon from '../icons.jsx'
import InboxChips from './InboxChips.jsx'
import { api, timeAgo } from '../api.js'

const FILTERS = [['all', 'همه'], ['unread', 'خوانده‌نشده'], ['unanswered', 'پاسخ‌داده‌نشده'], ['answered', 'پاسخ‌داده‌شده']]

export default function Comments() {
  const [filter, setFilter] = useState('unanswered')
  const [items, setItems] = useState([])
  const [open, setOpen] = useState(null)
  const [text, setText] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () => api.get(`/api/comments?filter=${filter}`).then(setItems).catch(() => {})
  useEffect(() => { load() }, [filter])

  function toggle(c) {
    if (open === c.id) return setOpen(null)
    setOpen(c.id); setText(''); setMsg('')
    if (!c.read) api.post(`/api/comments/${c.id}/read`).then(() => setItems((xs) => xs.map((x) => x.id === c.id ? { ...x, read: 1 } : x)))
  }

  async function send(kind, c) {
    setBusy(true); setMsg('')
    try {
      await api.post(`/api/comments/${c.id}/${kind}`, { text })
      setMsg(kind === 'reply' ? 'پاسخ عمومی ثبت شد ✅' : 'دایرکت خصوصی فرستاده شد ✅')
      setText(''); load()
    } catch (e) { setMsg(e.message) }
    finally { setBusy(false) }
  }

  async function setHidden(c, hide) {
    setBusy(true); setMsg('')
    try {
      await api.post(`/api/comments/${c.id}/hide`, { hide })
      setMsg(hide ? 'کامنت مخفی شد ✅' : 'کامنت دوباره نمایش داده می‌شود ✅'); load()
    } catch (e) { setMsg(e.message) }
    finally { setBusy(false) }
  }

  async function block(c) {
    if (!confirm(`ربات دیگر به ${c.username || c.user_id} جواب ندهد؟`)) return
    await api.post('/api/ai/blocked', { user_id: c.user_id, username: c.username, reason: 'از صفحه‌ی کامنت‌ها' })
    setMsg('کاربر مسدود شد ✅')
  }

  return (
    <>
      <header className="topbar"><div className="title"><h1>کامنت‌ها</h1><span className="sub">کامنت‌های پست‌ها و ریلزها</span></div><span className="actions"><button className="btn sm" onClick={load}>تازه‌سازی</button><a href="#/more" className="iconbtn" aria-label="بیشتر"><Icon n="gear" /></a></span></header>
      <InboxChips cur="comments" />
      <div className="chips">{FILTERS.map(([k, l]) => <button key={k} className={`chip ${filter === k ? 'active' : ''}`} onClick={() => setFilter(k)}>{l}</button>)}</div>
      {!items.length && <div className="empty">کامنتی در این فیلتر نیست</div>}
      <div className="list">
        {items.map((c) => (
          <div key={c.id} className={`item ${c.read ? '' : 'unread'}`} onClick={() => toggle(c)}>
            <div className="row">
              <span className="who">{c.username || c.user_id} {c.hidden ? <span className="pill muted">مخفی{c.hidden_reason ? `: ${c.hidden_reason}` : ''}</span> : c.answered ? <span className="pill good">پاسخ داده شد</span> : <span className="pill warn">بی‌پاسخ</span>}</span>
              <span className="when">{timeAgo(c.created_at)}</span>
            </div>
            <div className="text">{c.text}</div>
            {open === c.id && (
              <div className="replybox" onClick={(e) => e.stopPropagation()}>
                <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="متن پاسخ…" />
                <div className="actions">
                  <button className="btn primary" disabled={busy || !text.trim()} onClick={() => send('reply', c)}>پاسخ عمومی</button>
                  <button className="btn" disabled={busy || !text.trim()} onClick={() => send('private', c)}>دایرکت خصوصی</button>
                  <button className="btn" disabled={busy} onClick={() => setHidden(c, !c.hidden)}>{c.hidden ? 'نمایش دوباره' : 'مخفی کردن'}</button>
                  <button className="btn danger" disabled={busy} onClick={() => block(c)}>مسدود</button>
                  <a className="btn" href={`#/customers/ig:${c.user_id}`}>پرونده</a>
                </div>
                {msg && <p className={msg.includes('✅') ? 'ok' : 'err'}>{msg}</p>}
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  )
}
