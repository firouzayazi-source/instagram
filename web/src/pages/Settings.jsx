import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import { ChannelList } from './Channels.jsx'
import { Switch } from './Rules.jsx'

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
    try { await api.del('/api/push/subscribe', { endpoint: sub.endpoint }) } catch { /* سرور در دسترس نبود؛ اشتراک مرورگر باز هم لغو شود */ }
    try { await sub.unsubscribe(); setSub(null); setMsg('اعلان غیرفعال شد') } catch (e) { setMsg('غیرفعال نشد: ' + e.message) }
  }

  async function setMode(mode) {
    try { await api.put('/api/settings', { push_mode: mode }); setS({ ...s, push_mode: mode }) } catch (e) { setMsg('ذخیره نشد: ' + e.message) }
  }

  async function logout() { await api.post('/api/logout'); onLogout() }

  const standalone = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone

  return (
    <>
      <header className="topbar"><h1>تنظیمات</h1></header>
      <Brake />
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
        <Devices />
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
  const problem = f.next && f.next.length < 8 ? 'دست‌کم ۸ نویسه' : f.next && !/^[A-Za-z0-9!@%^*_+=.,:/?~-]+$/.test(f.next) ? 'فقط حرف انگلیسی، عدد و ! @ % ^ * _ + = . , : / ? ~ -' : f.again && f.again !== f.next ? 'تکرار یکی نیست' : ''

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
      <div className="field"><label>رمز تازه (دست‌کم ۸ نویسه، بدون فاصله)</label>
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


// دستگاه‌های شناخته‌شده: فقط همین‌ها با رمز وارد می‌شوند؛ دستگاه تازه منتظر تأیید از یکی از این‌ها می‌ماند
function Devices() {
  const [d, setD] = useState(null)
  const [msg, setMsg] = useState(null)
  const load = () => api.get('/api/devices').then(setD).catch(() => {})
  useEffect(() => { load() }, [])
  if (!d) return null
  const when = (t) => new Date(t * 1000).toLocaleString('fa-IR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Tehran' })
  async function act(x, action) {
    if (action === 'revoke' && !confirm(`«${x.name}» از فهرست برداشته شود؟ همان لحظه از پنل خارج می‌شود و دیگر با رمز هم وارد نمی‌شود.`)) return
    setMsg(null)
    try { setD(await api.post(`/api/devices/${x.id}/${action}`)); setMsg({ ok: true, text: action === 'approve' ? 'تأیید شد ✅ حالا روی آن دستگاه دوباره وارد شوید.' : 'برداشته شد' }) }
    catch (ex) { setMsg({ ok: false, text: ex.message }) }
  }
  async function lock(on) {
    if (!on && !confirm('با خاموش شدن قفل، هر دستگاهی که رمز را بداند وارد می‌شود. خاموش شود؟')) return
    try { setD(await api.put('/api/devices/lock', { on })) } catch (ex) { setMsg({ ok: false, text: ex.message }) }
  }
  return (
    <div style={{ marginTop: 16 }}>
      <h3>دستگاه‌ها {d.lock ? <span className="pill good">فقط دستگاه‌های شناخته‌شده</span> : <span className="pill warn">هر دستگاه با رمز</span>}</h3>
      <p className="muted">دستگاه تازه حتی با رمز درست وارد نمی‌شود تا از همین‌جا تأییدش کنید؛ برای هر درخواست به تلگرام هم خبر می‌آید. اگر همه‌ی دستگاه‌ها از دست رفت، روی سرور: <code dir="ltr">sudo python3 /opt/igbot/tools/reset_panel_password.py --apply</code></p>
      <div className="list">
        {d.items.map((x) => (
          <div key={x.id} className="item" style={{ cursor: 'default' }}>
            <div className="row">
              <b>{x.name || 'دستگاه'} {x.current && <span className="pill good">همین دستگاه</span>} {x.status === 'pending' && <span className="pill warn">منتظر تأیید</span>}</b>
              <span className="when">{when(x.last_seen)}</span>
            </div>
            <small className="muted" dir="ltr">{x.last_ip}</small>
            {!x.current && (
              <div className="actions" style={{ marginTop: 6 }}>
                {x.status === 'pending' && <button className="btn sm primary" onClick={() => act(x, 'approve')}>تأیید، خودم هستم</button>}
                <button className="btn sm danger" onClick={() => act(x, 'revoke')}>{x.status === 'pending' ? 'رد' : 'برداشتن'}</button>
              </div>
            )}
          </div>
        ))}
      </div>
      <label className="check" style={{ marginTop: 8 }}><input type="checkbox" checked={d.lock} onChange={(e) => lock(e.target.checked)} /> فقط دستگاه‌های شناخته‌شده وارد شوند (پیشنهادی)</label>
      {msg && <p className={msg.ok ? 'ok' : 'err'}>{msg.text}</p>}
    </div>
  )
}


// توقف اضطراری (app/safety.py): با خطای محدودیت یا مسدودی از اینستاگرام خودکار روشن می‌شود؛ فقط صاحب پیج خاموشش می‌کند
function Brake() {
  const [b, setB] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { api.get('/api/safety/brake').then(setB).catch(() => setB({})) }, [])
  async function set(on) {
    if (!confirm(on ? 'همه‌ی جواب‌ها، دایرکت‌ها و انتشارهای خودکار همین الان متوقف شود؟'
      : 'مطمئنید پیج سالم است (صفحه‌ی Account Status اینستاگرام مشکلی نشان نمی‌دهد) و ارسال خودکار دوباره شروع شود؟')) return
    setBusy(true)
    try { setB(await api.post('/api/safety/brake', { on })) } catch (ex) { alert(ex.message) } finally { setBusy(false) }
  }
  if (!b) return null
  return (
    <section className="card">
      <div className="row-between">
        <h2 style={{ margin: 0 }}>⛔ توقف اضطراری</h2>
        <Switch checked={!!b.on} onChange={(v) => !busy && set(v)} label="توقف اضطراری" />
      </div>
      {b.on
        ? <p className="err" style={{ margin: '8px 0 0' }}>روشن است: هیچ جواب، دایرکت یا انتشاری از برنامه روی پیج نمی‌رود؛ پیام‌ها فقط در صندوق ثبت می‌شوند.{b.reason ? <><br /><small>علت: {b.reason}</small></> : null}</p>
        : <p className="muted" style={{ margin: '8px 0 0' }}>خاموش: برنامه عادی کار می‌کند. اگر اینستاگرام محدودیت یا مسدودی نشان بدهد، خودش روشن می‌شود و به تلگرام خبر می‌دهد.</p>}
    </section>
  )
}
