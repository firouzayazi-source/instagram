import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'

// ورود با رمز، یا با گوگل (فقط ایمیل‌های مجاز). اگر مرورگر با همان ایمیل به گوگل وصل باشد، خودکار وارد می‌شود.
export default function Login({ onLogin }) {
  const [pw, setPw] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const gbox = useRef(null)

  useEffect(() => {
    let alive = true
    api.get('/api/login/google').then((g) => {
      if (!alive || !g.enabled) return
      const start = () => {
        if (!alive || !window.google?.accounts?.id) return
        window.google.accounts.id.initialize({
          client_id: g.client_id,
          auto_select: true,                       // ایمیلِ وارد شده‌ی گوگل ← ورود بی‌کلیک
          cancel_on_tap_outside: false,
          callback: async ({ credential }) => {
            setBusy(true); setErr('')
            try { await api.post('/api/login/google', { credential }); onLogin() }
            catch (ex) { setErr(ex.message) }
            finally { setBusy(false) }
          },
        })
        if (gbox.current) window.google.accounts.id.renderButton(gbox.current, { theme: 'outline', size: 'large', text: 'signin_with', locale: 'fa' })
        window.google.accounts.id.prompt()
      }
      if (window.google?.accounts?.id) return start()
      const s = document.createElement('script')
      s.src = 'https://accounts.google.com/gsi/client'; s.async = true; s.onload = start
      document.head.appendChild(s)
    }).catch(() => {})
    return () => { alive = false }
  }, [])

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setErr('')
    try { await api.post('/api/login', { password: pw }); onLogin() }
    catch (ex) { setErr(ex.message) }
    finally { setBusy(false) }
  }

  return (
    <main>
      <form className="card login" onSubmit={submit}>
        <h2>ورود به پنل استوک لند</h2>
        <div ref={gbox} style={{ display: 'flex', justifyContent: 'center', marginBottom: 8 }} />
        <div className="field">
          <label htmlFor="pw">رمز پنل</label>
          <input id="pw" type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoFocus autoComplete="current-password" />
        </div>
        {err && <p className="err">{err}</p>}
        <button className="btn primary" disabled={busy || !pw}>ورود</button>
      </form>
    </main>
  )
}
