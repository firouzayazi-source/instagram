import React, { useState } from 'react'
import { api } from '../api.js'

// ورود با رمز پنل
export default function Login({ onLogin }) {
  const [pw, setPw] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState('')

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setErr(''); setPending('')
    try { await api.post('/api/login', { password: pw }); onLogin() }
    catch (ex) { if (ex.status === 403 && ex.message.includes('شناخته‌شده نیست')) setPending(ex.message); else setErr(ex.message) }
    finally { setBusy(false) }
  }

  return (
    <main className="login-screen">
      <form className="card login" onSubmit={submit}>
        <div className="login-brand"><b>استوک لند</b><span>پنل پاسخ‌گویی و فروش</span></div>
        <div className="field">
          <label htmlFor="pw">رمز پنل</label>
          <input id="pw" type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoFocus autoComplete="current-password" />
        </div>
        {err && <p className="err">{err}</p>}
        {pending && <div className="note warn" style={{ marginBottom: 10 }}>🔐 {pending}</div>}
        <button className="btn primary block big" disabled={busy || !pw}>{busy ? 'در حال ورود…' : 'ورود'}</button>
      </form>
    </main>
  )
}
