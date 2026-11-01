import React, { useState } from 'react'
import { api } from '../api.js'

export default function Login({ onLogin }) {
  const [pw, setPw] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

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
