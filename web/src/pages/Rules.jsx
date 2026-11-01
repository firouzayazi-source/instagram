import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

const MATCH = { any: 'هر مقداری', exact: 'برابر دقیق', contains: 'شامل', starts_with: 'شروع با', regex: 'الگو' }

export default function Rules() {
  const [rules, setRules] = useState([])
  const [test, setTest] = useState({ channel: 'comment', text: '' })
  const [result, setResult] = useState(null)

  const load = () => api.get('/api/rules').then(setRules).catch(() => {})
  useEffect(() => { load() }, [])

  async function toggle(r) {
    await api.post(`/api/rules/${r.id}/enable`, { enabled: !r.enabled })
    load()
  }
  async function runTest(e) {
    e.preventDefault()
    const res = await api.post('/api/rules/test', test)
    setResult(res.rule ? `به قانون «${res.rule.name}» می‌خورد` : 'به هیچ قانونی نمی‌خورد')
  }

  return (
    <>
      <header className="topbar"><h1>پاسخ هوشمند</h1><a href="#/rules/new" className="btn primary sm">+ دستور جدید</a></header>
      <form className="card" onSubmit={runTest}>
        <h2>آزمایش</h2>
        <div className="trigger">
          <select value={test.channel} onChange={(e) => setTest({ ...test, channel: e.target.value })}>
            <option value="comment">کامنت</option><option value="dm">دایرکت</option>
          </select>
          <input type="text" value={test.text} onChange={(e) => setTest({ ...test, text: e.target.value })} placeholder="مثلاً: تقویم رو میخوام" />
          <button className="btn">بررسی</button>
        </div>
        {result && <p className="muted">{result}</p>}
      </form>
      {!rules.length && <div className="empty">هنوز دستوری ندارید</div>}
      <div className="list">
        {rules.map((r) => (
          <div key={r.id} className="item" style={{ cursor: 'default' }}>
            <div className="row">
              <span className="who">{r.name}</span>
              <label className="toggle"><input type="checkbox" checked={!!r.enabled} onChange={() => toggle(r)} /> فعال</label>
            </div>
            <div className="muted">
              {r.channels.map((c) => c === 'comment' ? 'کامنت' : 'دایرکت').join('، ')}
              {' · '}{r.triggers.map((t) => t.match === 'any' ? MATCH.any : `${MATCH[t.match]}: ${t.value}`).join(' یا ')}
              {r.post_scope !== 'all' && ' · محدود به پست'}
            </div>
            <div className="actions" style={{ marginTop: 6 }}>
              <a href={`#/rules/${r.id}`} className="btn sm">ویرایش</a>
              <span className="muted" style={{ alignSelf: 'center' }}>{r.use_count.toLocaleString('fa-IR')} بار اجرا شده</span>
            </div>
          </div>
        ))}
      </div>
    </>
  )
}
