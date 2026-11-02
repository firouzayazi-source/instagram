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
        <button className="btn danger" onClick={logout}>خروج از پنل</button>
      </section>
    </>
  )
}
