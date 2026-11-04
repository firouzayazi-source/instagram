import React, { useEffect, useState } from 'react'
import { api, fa, timeAgo } from '../api.js'
import { Msg } from './Ai.jsx'

const CH = { dm: 'دایرکت', comment: 'کامنت', telegram: 'تلگرام' }

// رضایت مشتری و آموخته‌ها: جوابی که مشتری پسندید به دانش آفلاین رفت؛ اینجا دیده و برگردانده می‌شود
export default function AiLearned() {
  const [d, setD] = useState(null)
  const [msg, setMsg] = useState(null)
  const load = () => api.get('/api/ai/learned').then(setD).catch(() => {})
  useEffect(() => { load() }, [])
  if (!d) return <div className="empty">در حال بارگذاری…</div>

  async function toggle(k, v) {
    setMsg(null)
    try { await api.put('/api/ai/settings', { [k]: v }); setD({ ...d, [k]: v }) }
    catch (ex) { setMsg({ ok: false, text: ex.message }) }
  }
  async function undo(id) {
    if (!confirm('این آموخته برگردانده شود؟ ربات دیگر از دانش آفلاین این جواب را نمی‌دهد.')) return
    try { await api.del(`/api/ai/learned/${id}`); setMsg({ ok: true, text: 'برگردانده شد ✅' }); load() }
    catch (ex) { setMsg({ ok: false, text: ex.message }) }
  }
  async function teach(id) {
    try { await api.post(`/api/ai/learned/from-log/${id}`); setMsg({ ok: true, text: 'یاد گرفت ✅' }); load() }
    catch (ex) { setMsg({ ok: false, text: ex.message }) }
  }
  const learnedLogs = new Set(d.items.map((x) => x.log_id))

  return (
    <>
      <section className="card">
        <h2>رضایت مشتری و یادگیری خودکار</h2>
        <div className="tiles">
          <div className="tile good"><b>{fa(d.stats.up)}</b><span>👍 پسندیده</span></div>
          <div className={`tile ${d.stats.down ? 'warn' : ''}`}><b>{fa(d.stats.down)}</b><span>👎 نپسندیده</span></div>
          <div className="tile"><b>{fa(d.stats.learned)}</b><span>آموخته در دانش آفلاین</span></div>
        </div>
        <label className="check"><input type="checkbox" checked={d.ask_feedback} onChange={(e) => toggle('ask_feedback', e.target.checked)} /> زیر جواب‌های هوش مصنوعی «👍 مفید بود / 👎 نه» بپرسد (اینستاگرام و تلگرام)</label>
        <label className="check"><input type="checkbox" checked={d.auto_learn} onChange={(e) => toggle('auto_learn', e.target.checked)} /> جوابی که مشتری پسندید خودکار به دانش آفلاین برود</label>
        <p className="hint muted">جواب آموخته دفعه‌ی بعد در همه‌ی کانال‌ها بی‌هزینه و فوری از موتور فهم داده می‌شود. جوابی که قیمت، موجودی یا لینک کالا دارد یاد گرفته نمی‌شود چون کهنه می‌شود؛ جواب‌های موتور فهم هم که خودشان آفلاین‌اند. «👎» پیام را به همکار می‌سپارد.</p>
        {!d.ready && <p className="err">دانش مشترک در دسترس نیست (ربات تلگرام روی سرور نیست)؛ یادگیری ثبت نمی‌شود.</p>}
        <Msg m={msg} />
      </section>

      <section className="card">
        <h2>آموخته‌ها</h2>
        {!d.items.length && <p className="muted">هنوز چیزی یاد گرفته نشده.</p>}
        <div className="list">
          {d.items.map((x) => (
            <div key={x.id} className="item" style={{ cursor: 'default' }}>
              <div className="row"><span className="who">❓ {x.question}</span><span className="when">{timeAgo(x.created_at)}</span></div>
              <div className="text" style={{ whiteSpace: 'pre-line' }}>{x.answer}</div>
              <div className="row" style={{ marginTop: 6 }}>
                <span className="pill muted">{CH[x.channel] || x.channel}</span>
                {x.status === 'learned' ? <button className="btn sm" onClick={() => undo(x.id)}>برگرداندن</button> : <span className="pill muted">برگردانده شد</span>}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="card">
        <h2>آخرین رأی‌های مشتری</h2>
        {!d.votes.length && <p className="muted">هنوز رأیی نیامده.</p>}
        <div className="list">
          {d.votes.map((v) => (
            <div key={v.id} className="item" style={{ cursor: 'default' }}>
              <div className="row"><span>{v.customer_vote === 'up' ? '👍' : '👎'} {v.input}</span><span className="when">{timeAgo(v.voted_at)}</span></div>
              <div className="text muted" style={{ whiteSpace: 'pre-line' }}>{v.reply}</div>
              {v.customer_vote === 'up' && !learnedLogs.has(v.id) && <button className="btn sm" style={{ marginTop: 6 }} onClick={() => teach(v.id)}>یاد بده</button>}
            </div>
          ))}
        </div>
      </section>
    </>
  )
}
