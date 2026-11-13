import React, { useEffect, useState } from 'react'
import { api, fa, timeAgo } from '../api.js'
import Icon from '../icons.jsx'

const WHERE = { comment: 'کامنت', dm: 'دایرکت', story_reply: 'جواب استوری', mention: 'منشن' }
const MATCH = { any: 'هر مقداری', exact: 'برابر', contains: 'شامل', starts_with: 'شروع با', regex: 'الگو' }

export function Switch({ checked, onChange, label }) {
  return <label className="switch" aria-label={label}><input type="checkbox" checked={!!checked} onChange={(e) => onChange(e.target.checked)} /><span /></label>
}

// پاسخ هوشمند: اکانت، وضعیت و فهرست دستورها
export default function Rules() {
  const [rules, setRules] = useState(null)
  const [ig, setIg] = useState(null)
  const [poll, setPoll] = useState(null)
  const [q, setQ] = useState('')
  const [search, setSearch] = useState(false)
  const load = () => api.get('/api/rules').then(setRules).catch(() => setRules([]))
  useEffect(() => {
    load()
    api.get('/api/channels').then((xs) => setIg(xs.find((x) => x.id === 'instagram'))).catch(() => {})
    api.get('/api/comment-poll').then(setPoll).catch(() => {})
  }, [])

  async function toggle(r, on) { await api.post(`/api/rules/${r.id}/enable`, { enabled: on }); load() }
  async function setChannel(on) {
    if (!on && !confirm('همه‌ی پاسخ‌های خودکار اینستاگرام خاموش شود؟ پیام‌ها همچنان در صندوق ثبت می‌شوند.')) return
    setIg(await api.put('/api/channels/instagram', { enabled: on }))
  }
  async function duplicate(r) { const { id } = await api.post(`/api/rules/${r.id}/copy`, { channels: r.channels }); location.hash = `#/rules/${id}` }
  async function remove(r) { if (confirm(`دستور «${r.name}» حذف شود؟`)) { await api.del(`/api/rules/${r.id}`); load() } }

  const shown = (rules || []).filter((r) => !q.trim() || (r.name + JSON.stringify(r.triggers) + JSON.stringify(r.actions)).includes(q.trim()))
  const st = poll?.status
  return (
    <>
      <header className="topbar">
        <div className="title"><h1>پاسخ هوشمند</h1><span className="sub">دستورهای دایرکت و کامنت</span></div>
        <a href="#/more" className="iconbtn" aria-label="بیشتر"><Icon n="gear" /></a>
      </header>

      <section className="sec">
        <div className="sec-h" style={{ alignItems: 'center' }}>
          <span className="ico"><Icon n="insta" /></span>
          <div className="grow">
            <h2>stock_land.ir</h2>
            <p>{ig ? (ig.enabled ? 'پاسخ خودکار روشن است' : 'پاسخ خودکار خاموش است') : '…'}
              {poll?.active && st && <> · {st.ok ? `بررسی کامنت‌ها ${timeAgo(st.at)}` : <span className="err">خطا در خواندن کامنت‌ها</span>}</>}</p>
          </div>
          {ig && <Switch checked={ig.enabled} onChange={setChannel} label="روشن و خاموش اینستاگرام" />}
        </div>
      </section>

      <section className="sec">
        <div className="sec-h">
          <div className="grow"><h2>دستورها</h2><p>شرط‌ها، پیام‌ها و وضعیت هر پاسخ هوشمند اینجا مدیریت می‌شود.</p></div>
        </div>
        <div className="sec-b">
          <div style={{ display: 'flex', gap: 10 }}>
            <a href="#/rules/new" className="btn primary big block" style={{ flex: 1 }}><Icon n="plus" /> دستور جدید</a>
            <button type="button" className="iconbtn" style={{ width: 52, height: 'auto' }} aria-label="جستجو" onClick={() => setSearch(!search)}><Icon n="search" /></button>
          </div>
          {search && <input type="text" autoFocus value={q} placeholder="جستجو در نام، کلمه یا متن پیام" onChange={(e) => setQ(e.target.value)} />}
        </div>
        {rules === null && <div className="empty">در حال بارگذاری…</div>}
        {rules && !rules.length && <div className="empty">هنوز دستوری ندارید. با «دستور جدید» شروع کنید؛ مثلاً هر کس زیر پست «قیمت» نوشت، لینک ربات را در دایرکت بگیرد.</div>}
        <div style={{ borderTop: shown.length ? '1px solid var(--line)' : 0 }}>
          {shown.map((r) => {
            const toComment = (r.actions.private_replies || [])[0], toDm = (r.actions.dm_replies || [])[0]
            return (
              <div key={r.id} className="rule" style={r.enabled ? undefined : { opacity: 0.6 }}>
                <div className="rh">
                  <b>{r.name}</b>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><small className="muted">{r.enabled ? 'فعال' : 'خاموش'}</small><Switch checked={r.enabled} onChange={(on) => toggle(r, on)} label="فعال" /></span>
                </div>
                <div>
                  {r.channels.map((c) => <span key={c} className="tag">{WHERE[c]}</span>)}
                  {r.post_scope !== 'all' && <span className="tag">{r.post_scope.includes('next') ? 'پست بعدی' : `${fa(r.post_scope.length)} پست خاص`}</span>}
                </div>
                <small className="muted">شرط: {r.triggers.map((t) => (t.match === 'any' ? MATCH.any : `${MATCH[t.match]} «${t.value}»`)).join(' یا ')}</small>
                {toComment && r.channels.includes('comment') && <small className="muted" style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>به کامنت: {toComment}</small>}
                {toDm && r.channels.some((c) => c !== 'comment') && <small className="muted" style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>به دایرکت و استوری: {toDm}</small>}
                <div className="actions" style={{ marginTop: 4 }}>
                  <a href={`#/rules/${r.id}`} className="btn sm"><Icon n="edit" /> ویرایش</a>
                  <button type="button" className="btn sm" onClick={() => duplicate(r)}><Icon n="copy" /> کپی</button>
                  <button type="button" className="iconbtn" style={{ width: 36, height: 36 }} aria-label="حذف" onClick={() => remove(r)}><Icon n="trash" /></button>
                  <small className="muted" style={{ alignSelf: 'center', marginInlineStart: 'auto' }}>{fa(r.use_count)} بار اجرا</small>
                </div>
              </div>
            )
          })}
        </div>
      </section>
    </>
  )
}
