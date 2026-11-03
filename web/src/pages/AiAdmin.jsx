import React, { useState } from 'react'
import { api, usd } from '../api.js'

const OP_FA = { intent_upsert: 'نیت دانش مرکزی', intent_delete: 'حذف نیت', section_set: 'متن بخش', setting: 'تنظیم' }

function OpView({ o }) {
  if (o.op === 'setting') return <span>{o.key} ← <code>{JSON.stringify(o.value)}</code></span>
  if (o.op === 'section_set') return <span>بخش {o.key}:<div className="preview">{o.text}</div></span>
  if (o.op === 'intent_delete') return <span>{o.id}</span>
  return (
    <span>{o.id ? `ویرایش ${o.id}` : 'نیت تازه'} · کلیدواژه‌ها: {(o.keys || []).join('، ') || '—'}{o.action ? ` · کار: ${o.action}` : ''}
      {o.answer && <div className="preview">{o.answer}</div>}</span>
  )
}

// تنظیم ربات با حرف زدن: هوش مصنوعی پیشنهاد می‌دهد، شما تأیید می‌کنید
export default function AiAdmin() {
  const [text, setText] = useState('')
  const [chat, setChat] = useState([])
  const [pending, setPending] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function send(e) {
    e.preventDefault()
    const t = text.trim()
    if (!t) return
    setBusy(true); setErr('')
    const history = chat.map((m) => ({ role: m.role, content: m.text }))
    setChat((c) => [...c, { role: 'user', text: t }]); setText('')
    try {
      const r = await api.post('/api/ai/admin-chat', { text: t, history })
      setChat((c) => [...c, { role: 'assistant', text: r.reply || '—', cost: r.cost }])
      setPending(r.ops.length ? r.ops : null)
    } catch (ex) { setErr(ex.message) }
    finally { setBusy(false) }
  }

  async function apply() {
    setBusy(true); setErr('')
    try {
      const r = await api.post('/api/ai/admin-apply', { ops: pending })
      setChat((c) => [...c, { role: 'assistant', text: r.results.join('\n') }]); setPending(null)
    } catch (ex) { setErr(ex.message) }
    finally { setBusy(false) }
  }

  return (
    <>
      <section className="card">
        <h2>تنظیم ربات با حرف</h2>
        <p className="muted">بنویسید چه چیزی در جواب‌های ربات عوض شود؛ برای اینستاگرام و تلگرام با هم. مثلاً: «شرایط اقساط رو ۶ ماهه با پیش‌پرداخت ۳۰٪ کن»، «به کسی که گارانتی پرسید بگو ۱۸ ماه گارانتی داریم»، «لحن رو خودمونی‌تر کن». هیچ تغییری بدون تأیید شما ذخیره نمی‌شود.</p>
        <div className="chat">
          {chat.map((m, i) => <div key={i} className={`bubble ${m.role === 'user' ? 'me' : 'bot'}`}>{m.text}{m.cost ? <div className="muted" style={{ fontSize: 11 }}>{usd(m.cost)}</div> : null}</div>)}
        </div>
        <form onSubmit={send} className="actions" style={{ marginTop: 8 }}>
          <textarea rows={2} style={{ flex: 1 }} value={text} disabled={busy} placeholder="چه چیزی عوض شود؟" onChange={(e) => setText(e.target.value)} />
          <button className="btn primary" disabled={busy || !text.trim()}>{busy ? '…' : 'بفرست'}</button>
        </form>
        {err && <p className="err">{err}</p>}
      </section>
      {pending && (
        <section className="card">
          <h2>تغییرهای پیشنهادی</h2>
          <div className="list">
            {pending.map((o, i) => (
              <div key={i} className="item" style={{ cursor: 'default' }}>
                <div className="row"><span className="pill warn">{OP_FA[o.op]}</span>
                  <button className="btn sm" onClick={() => setPending(pending.filter((_, j) => j !== i).length ? pending.filter((_, j) => j !== i) : null)}>✕ حذف از پیشنهاد</button></div>
                <div className="text"><OpView o={o} /></div>
              </div>
            ))}
          </div>
          <div className="actions" style={{ marginTop: 8 }}>
            <button className="btn primary" disabled={busy} onClick={apply}>تأیید و ذخیره</button>
            <button className="btn" onClick={() => setPending(null)}>رد همه</button>
          </div>
          <p className="hint muted">تغییرهای دانش مرکزی را ربات تلگرام چند ثانیه بعد برمی‌دارد و از آن لحظه هر دو پلتفرم با متن تازه جواب می‌دهند.</p>
        </section>
      )}
    </>
  )
}
