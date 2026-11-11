import React, { useState } from 'react'
import { api, usd } from '../api.js'
import { Msg } from './Ai.jsx'

// دستیار محتوا: ایده‌ی ریلز از روی آمار پیج؛ فقط پیش‌نویس، هیچ‌چیز منتشر نمی‌شود
export default function Ideas() {
  const [topic, setTopic] = useState('')
  const [d, setD] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)

  async function go(e) {
    e.preventDefault(); setBusy(true); setMsg(null)
    try { setD(await api.post('/api/content/ideas', { topic })) } catch (ex) { setMsg({ ok: false, text: ex.message }) }
    setBusy(false)
  }
  function makeRule(x) {
    sessionStorage.setItem('rule_prefill', JSON.stringify({
      name: x.title.slice(0, 40), channels: ['comment'], post_scope: [],
      triggers: [{ match: 'contains', value: x.keyword }],
      actions: { private_replies: [x.dm_text], public_replies: [x.public_reply] },
    }))
    location.hash = '#/rules/new'
  }
  const copy = (t) => navigator.clipboard?.writeText(t).then(() => setMsg({ ok: true, text: 'کپی شد ✅' })).catch(() => {})

  return (
    <>
      <form className="card" onSubmit={go}>
        <h2>ایده‌ی محتوا</h2>
        <p className="muted">از روی آمار واقعی پیج سه ایده‌ی ریلز می‌دهد: متن ثانیه‌ی اول، صحنه‌ها، کپشن و کلمه‌ی کامنت. پیش‌نویس است؛ پیش از ضبط، درستی ترفند را خودتان روی گوشی امتحان کنید.</p>
        <div className="field">
          <label>موضوع (اختیاری)</label>
          <input type="text" value={topic} maxLength="300" placeholder="مثلاً: مشکل پر شدن حافظه، یا خالی بگذارید" onChange={(e) => setTopic(e.target.value)} />
        </div>
        <button className="btn primary" disabled={busy}>{busy ? 'در حال فکر کردن…' : 'سه ایده بده'}</button>
        <Msg m={msg} />
        {d && <p className="hint muted">{d.model} · {usd(d.cost)}{!d.has_stats && ' · هنوز آمار پیج ذخیره نشده؛ در «تحلیل محتوا» دکمه‌ی «بگیر همین الان» را بزنید تا ایده‌ها دقیق‌تر شوند.'}</p>}
      </form>
      {(d?.ideas || []).map((x, i) => (
        <section key={i} className="card">
          <h3>{x.title}</h3>
          <p className="muted">{x.why}</p>
          <p><b>ثانیه‌ی اول، روی تصویر:</b> {x.hook}</p>
          <ol style={{ margin: '6px 0', paddingInlineStart: 20 }}>{x.scenes.map((s, j) => <li key={j}>{s}</li>)}</ol>
          <p style={{ whiteSpace: 'pre-wrap' }}><b>کپشن:</b> {x.caption}</p>
          <p className="muted">کلمه‌ی کامنت: «{x.keyword}» · دایرکت: {x.dm_text}</p>
          <div className="actions">
            <button className="btn sm" onClick={() => copy(x.caption)}>کپی کپشن</button>
            <button className="btn sm primary" onClick={() => makeRule(x)}>ساخت دستور کامنت</button>
          </div>
        </section>
      ))}
    </>
  )
}
