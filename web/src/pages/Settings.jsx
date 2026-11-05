import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { ChannelList } from './Channels.jsx'

function b64ToArray(b64) {
  const s = (b64 + '='.repeat((4 - (b64.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/')
  return Uint8Array.from(atob(s), (c) => c.charCodeAt(0))
}

export default function Settings({ onLogout }) {
  const [s, setS] = useState({})
  const [sub, setSub] = useState(null)
  const [msg, setMsg] = useState('')
  const supported = 'serviceWorker' in navigator && 'PushManager' in window

  useEffect(() => {
    api.get('/api/settings').then(setS).catch(() => {})
    if (supported) navigator.serviceWorker.ready.then((reg) => reg.pushManager.getSubscription()).then(setSub).catch(() => {})
  }, [])

  async function enablePush() {
    setMsg('')
    try {
      if (Notification.permission === 'denied') return setMsg('اجازه‌ی اعلان در مرورگر رد شده؛ از تنظیمات گوشی فعالش کنید.')
      const reg = await navigator.serviceWorker.ready
      const ps = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToArray(s.vapid_public_key) })
      await api.post('/api/push/subscribe', ps.toJSON())
      setSub(ps); setMsg('اعلان روی این دستگاه فعال شد ✅')
    } catch (e) { setMsg('فعال‌سازی ناموفق: ' + e.message) }
  }

  async function disablePush() {
    await api.del('/api/push/subscribe', { endpoint: sub.endpoint })
    await sub.unsubscribe(); setSub(null); setMsg('اعلان غیرفعال شد')
  }

  async function setMode(mode) {
    await api.put('/api/settings', { push_mode: mode }); setS({ ...s, push_mode: mode })
  }

  async function logout() { await api.post('/api/logout'); onLogout() }

  const standalone = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone

  return (
    <>
      <header className="topbar"><h1>تنظیمات</h1></header>
      <section className="card">
        <h2>کانال‌ها و اتصال‌ها</h2>
        <p className="muted">هر شبکه جدا روشن و خاموش می‌شود. همه از مغز مرکزی و دانش مرکزی جواب می‌دهند.</p>
        <ChannelList />
      </section>
      <section className="card">
        <h2>اعلان روی گوشی</h2>
        {!supported && <p className="muted">این مرورگر اعلان پوش ندارد.</p>}
        {supported && !standalone && <p className="muted">برای اعلان در آیفون، اول صفحه را با «Add to Home Screen» نصب کنید و از همان‌جا باز کنید.</p>}
        {supported && !s.push_enabled && <p className="muted">کلید VAPID روی سرور تنظیم نشده (`python -m app.push --gen`).</p>}
        {supported && s.push_enabled && (
          <div className="actions">
            {sub ? <button className="btn" onClick={disablePush}>غیرفعال کردن اعلان این دستگاه</button>
                 : <button className="btn primary" onClick={enablePush}>فعال کردن اعلان این دستگاه</button>}
          </div>
        )}
        {msg && <p className={msg.includes('✅') ? 'ok' : 'err'}>{msg}</p>}
        <div className="field" style={{ marginTop: 12 }}>
          <label>چه وقت اعلان بیاید؟</label>
          <select value={s.push_mode || 'unanswered'} onChange={(e) => setMode(e.target.value)}>
            <option value="unanswered">فقط وقتی ربات جواب خودکار نداشت (پیشنهادی)</option>
            <option value="all">هر کامنت و دایرکت</option>
            <option value="off">هیچ‌وقت</option>
          </select>
        </div>
      </section>
      <section className="card">
        <h2>حساب</h2>
        <PasswordForm />
        <GoogleLogin />
        <button className="btn danger" onClick={logout} style={{ marginTop: 12 }}>خروج از پنل</button>
      </section>
    </>
  )
}


// تغییر رمز پنل؛ رمز فقط در ‎.env سرور نوشته می‌شود و دستگاه‌های دیگر خارج می‌شوند
function PasswordForm() {
  const [f, setF] = useState({ current: '', next: '', again: '' })
  const [show, setShow] = useState(false)
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const problem = f.next && f.next.length < 4 ? 'دست‌کم ۴ نویسه' : /\s/.test(f.next) ? 'بدون فاصله' : f.again && f.again !== f.next ? 'تکرار یکی نیست' : ''

  async function save(e) {
    e.preventDefault(); setMsg(null); setBusy(true)
    try {
      await api.post('/api/password', { current: f.current, new: f.next })
      setF({ current: '', next: '', again: '' })
      setMsg({ ok: true, text: 'رمز عوض شد ✅ از این به بعد با رمز تازه وارد شوید؛ دستگاه‌های دیگر خارج شدند. رمز را جایی امن یادداشت کنید.' })
    } catch (ex) { setMsg({ ok: false, text: ex.message }) }
    setBusy(false)
  }

  const type = show ? 'text' : 'password'
  return (
    <form onSubmit={save}>
      <h3 style={{ marginTop: 0 }}>تغییر رمز پنل</h3>
      <div className="field"><label>رمز فعلی</label>
        <input type={type} dir="ltr" autoComplete="current-password" value={f.current} onChange={set('current')} /></div>
      <div className="field"><label>رمز تازه (دست‌کم ۴ نویسه، بدون فاصله)</label>
        <input type={type} dir="ltr" autoComplete="new-password" value={f.next} onChange={set('next')} /></div>
      <div className="field"><label>تکرار رمز تازه</label>
        <input type={type} dir="ltr" autoComplete="new-password" value={f.again} onChange={set('again')} /></div>
      <label className="check-row"><input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} /> نمایش رمزها</label>
      {problem && <p className="err">{problem}</p>}
      <div className="actions" style={{ marginTop: 8 }}>
        <button className="btn primary" disabled={busy || !f.current || !f.next || f.next !== f.again || !!problem}>{busy ? 'در حال ذخیره…' : 'تغییر رمز'}</button>
      </div>
      <p className="muted">اگر رمز را فراموش کردید، روی سرور: <code dir="ltr">sudo python3 /opt/igbot/tools/reset_panel_password.py --apply</code></p>
      {msg && <p className={msg.ok ? 'ok' : 'err'}>{msg.text}</p>}
    </form>
  )
}


// ورود با گوگل: شناسه‌ی عمومی دکمه (از Google Cloud) و ایمیل‌های مجاز؛ در ‎.env سرور ذخیره می‌شود
const GKEYS = ['GOOGLE_CLIENT_ID', 'LOGIN_EMAILS']
function GoogleLogin() {
  const [items, setItems] = useState(null)
  const [draft, setDraft] = useState({})
  const [msg, setMsg] = useState(null)
  useEffect(() => { api.get('/api/ai/keys').then((r) => setItems(r.items.filter((x) => GKEYS.includes(x.name)))).catch(() => {}) }, [])
  if (!items) return null

  async function save(name) {
    setMsg(null)
    try {
      const r = await api.put(`/api/ai/keys/${name}`, { value: draft[name] || '' })
      setItems(r.items.filter((x) => GKEYS.includes(x.name))); setDraft({ ...draft, [name]: '' })
      setMsg({ ok: true, text: 'ذخیره شد ✅' })
    } catch (ex) { setMsg({ ok: false, text: ex.message }) }
  }

  const on = items.every((x) => x.set)
  return (
    <div style={{ marginTop: 16 }}>
      <h3>ورود با گوگل {on ? <span className="pill good">روشن</span> : <span className="pill muted">خاموش</span>}</h3>
      <p className="muted">اگر گوشی یا مرورگر با یکی از این ایمیل‌ها به گوگل وصل باشد، پنل خودکار وارد می‌شود. ورود با رمز هم همیشه می‌ماند.</p>
      {items.map((x) => (
        <div key={x.name} className="field">
          <label>{x.label} {x.set ? <span className="pill good" dir="ltr">{x.hint}</span> : <span className="pill muted">ندارد</span>}</label>
          <div className="actions">
            <input dir="ltr" style={{ flex: 1 }} value={draft[x.name] || ''} onChange={(e) => setDraft({ ...draft, [x.name]: e.target.value })}
              placeholder={x.name === 'LOGIN_EMAILS' ? 'you@gmail.com' : '1234…apps.googleusercontent.com'} />
            <button type="button" className="btn sm primary" disabled={!(draft[x.name] || '').trim()} onClick={() => save(x.name)}>ثبت</button>
          </div>
        </div>
      ))}
      {msg && <p className={msg.ok ? 'ok' : 'err'}>{msg.text}</p>}
    </div>
  )
}
