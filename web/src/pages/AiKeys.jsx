import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

const HIDE = ['GOOGLE_CLIENT_ID', 'LOGIN_EMAILS']   // در «تنظیمات ← حساب»

// کلید سرویس‌های هوش مصنوعی: در ‎.env سرور نوشته می‌شود و هیچ‌وقت به پنل برنمی‌گردد (فقط چهار نویسه‌ی آخر)
export default function AiKeys() {
  const [items, setItems] = useState(null)
  const [draft, setDraft] = useState({})
  const [msg, setMsg] = useState({})
  const [open, setOpen] = useState(false)
  useEffect(() => { api.get('/api/ai/keys').then((r) => setItems(r.items.filter((x) => !HIDE.includes(x.name)))).catch(() => {}) }, [])
  if (!items) return null

  async function save(name, value) {
    setMsg({ ...msg, [name]: null })
    try {
      const r = await api.put(`/api/ai/keys/${name}`, { value })
      setItems(r.items.filter((x) => !HIDE.includes(x.name))); setDraft({ ...draft, [name]: '' })
      setMsg({ ...msg, [name]: { ok: true, text: value ? 'ثبت شد ✅ همین الان فعال است' : 'حذف شد' } })
      window.dispatchEvent(new Event('ai:keys'))
    } catch (ex) { setMsg({ ...msg, [name]: { ok: false, text: ex.message } }) }
  }

  const setCount = items.filter((x) => x.secret && x.set).length
  return (
    <section className="card">
      <div className="row-between">
        <h2 style={{ margin: 0 }}>کلید سرویس‌های هوش مصنوعی</h2>
        <button type="button" className="btn sm" onClick={() => setOpen(!open)}>{open ? 'بستن' : setCount ? `${setCount.toLocaleString('fa-IR')} کلید ثبت شده · ویرایش` : 'افزودن کلید'}</button>
      </div>
      <p className="hint muted">کلید فقط در فایل ‎.env خود سرور ذخیره می‌شود، از همین‌جا عوض یا حذف می‌شود و دیگر نمایش داده نمی‌شود؛ فقط چهار نویسه‌ی آخرش برای شناسایی دیده می‌شود. کلید را جای دیگری (چت، پیام) نفرستید.</p>
      {open && items.map((x) => (
        <div key={x.name} className="field">
          <label>{x.label} {x.set ? <span className="pill good">{x.secret ? `ثبت شده ${x.hint}` : x.hint}</span> : <span className="pill muted">ندارد</span>}</label>
          <div className="actions">
            <input type={x.secret ? 'password' : 'text'} dir="ltr" autoComplete="off" style={{ flex: 1 }}
              placeholder={x.secret ? (x.set ? 'کلید تازه برای جایگزینی' : 'کلید را اینجا بچسبانید') : (x.name === 'CUSTOM_AI_BASE_URL' ? 'https://…/v1' : '')}
              value={draft[x.name] || ''} onChange={(e) => setDraft({ ...draft, [x.name]: e.target.value })} />
            <button type="button" className="btn sm primary" disabled={!(draft[x.name] || '').trim()} onClick={() => save(x.name, draft[x.name])}>ثبت</button>
            {x.set && <button type="button" className="btn sm danger" onClick={() => confirm(`«${x.label}» حذف شود؟`) && save(x.name, '')}>حذف</button>}
          </div>
          {msg[x.name] && <p className={msg[x.name].ok ? 'ok' : 'err'}>{msg[x.name].text}</p>}
        </div>
      ))}
    </section>
  )
}
