import React, { useEffect, useRef, useState } from 'react'
import Icon from '../icons.jsx'
import InboxChips from './InboxChips.jsx'
import { api, timeAgo } from '../api.js'

const FILTERS = [['all', 'همه'], ['unread', 'خوانده‌نشده'], ['unanswered', 'پاسخ‌داده‌نشده'], ['answered', 'پاسخ‌داده‌شده']]

export default function Messages({ userId }) {
  return userId ? <Thread userId={userId} /> : <ConversationList />
}

function ConversationList() {
  const [filter, setFilter] = useState('all')
  const [items, setItems] = useState([])
  const load = () => api.get(`/api/conversations?filter=${filter}`).then(setItems).catch(() => {})
  useEffect(() => { load() }, [filter])
  return (
    <>
      <header className="topbar"><div className="title"><h1>پیام‌ها</h1><span className="sub">دایرکت‌های اینستاگرام</span></div><span className="actions"><button className="btn sm" onClick={load}>تازه‌سازی</button><a href="#/more" className="iconbtn" aria-label="بیشتر"><Icon n="gear" /></a></span></header>
      <InboxChips cur="messages" />
      <div className="chips">{FILTERS.map(([k, l]) => <button key={k} className={`chip ${filter === k ? 'active' : ''}`} onClick={() => setFilter(k)}>{l}</button>)}</div>
      {!items.length && <div className="empty">گفتگویی نیست</div>}
      <div className="list">
        {items.map((c) => (
          <a key={c.user_id} href={`#/messages/${c.user_id}`} className={`item ${c.read ? '' : 'unread'}`} style={{ color: 'inherit' }}>
            <div className="row">
              <span className="who">{c.username || c.user_id} {c.answered ? '' : <span className="pill warn">بی‌پاسخ</span>}</span>
              <span className="when">{timeAgo(c.last_at)}</span>
            </div>
            <div className="text" style={{ color: 'var(--muted)' }}>{c.last_text}</div>
          </a>
        ))}
      </div>
    </>
  )
}

function Thread({ userId }) {
  const [msgs, setMsgs] = useState([])
  const [text, setText] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [name, setName] = useState(userId)
  const [human, setHuman] = useState(0)
  const end = useRef(null)
  const loadHuman = () => api.get(`/api/conversations/${userId}/human`).then((r) => setHuman(r.until)).catch(() => {})

  const load = () => api.get(`/api/conversations/${userId}/messages`).then((m) => { setMsgs(m); setTimeout(() => end.current?.scrollIntoView(), 50) }).catch(() => {})
  useEffect(() => {
    load(); loadHuman()
    api.get('/api/conversations').then((cs) => { const c = cs.find((x) => x.user_id === userId); if (c?.username) setName(c.username) }).catch(() => {})
    const t = setInterval(load, 15000)
    return () => clearInterval(t)
  }, [userId])

  async function block() {
    if (!confirm(`ربات دیگر به ${name} جواب ندهد؟`)) return
    await api.post('/api/ai/blocked', { user_id: userId, username: name === userId ? null : name, reason: 'از صفحه‌ی پیام‌ها' })
    setErr('کاربر مسدود شد؛ ربات دیگر جوابش را نمی‌دهد.')
  }

  async function send(e) {
    e.preventDefault(); setBusy(true); setErr('')
    try { await api.post(`/api/conversations/${userId}/send`, { text }); setText(''); load(); loadHuman() }
    catch (ex) { setErr(ex.message) }
    finally { setBusy(false) }
  }

  return (
    <>
      <header className="topbar"><h1>{name}</h1><span className="actions"><a href={`#/customers/ig:${userId}`} className="btn sm">پرونده</a><button className="btn sm danger" onClick={block}>مسدود</button><a href="#/messages" className="btn sm">بازگشت</a></span></header>
      {human > Date.now() / 1000 && (
        <div className="card row-between" style={{ marginBottom: 8 }}>
          <span>🧑‍💼 گفتگو دست همکار است؛ ربات تا {new Date(human * 1000).toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' })} جواب نمی‌دهد.</span>
          <button className="btn sm" onClick={() => api.del(`/api/conversations/${userId}/human`).then(() => setHuman(0))}>🤖 برگرداندن به ربات</button>
        </div>
      )}
      <div className="thread">
        {msgs.map((m) => (
          <div key={m.id} className={`bubble ${m.direction}`}>{m.text}<span className="when">{m.sender === 'admin' ? '🧑‍💼 ' : m.sender === 'bot' ? '🤖 ' : ''}{timeAgo(m.created_at)}</span></div>
        ))}
        <div ref={end} />
      </div>
      <form className="replybox" onSubmit={send}>
        <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="پیام…" />
        {err && <p className="err">{err}</p>}
        <div className="actions"><button className="btn primary" disabled={busy || !text.trim()}>ارسال</button></div>
      </form>
      <p className="muted">اینستاگرام فقط تا ۲۴ ساعت بعد از آخرین پیام کاربر اجازه‌ی ارسال می‌دهد.</p>
    </>
  )
}
