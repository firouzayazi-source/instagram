import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

const EMPTY = {
  name: '', enabled: true, priority: 100, channels: ['comment'], post_scope: 'all',
  triggers: [{ match: 'any', value: '' }],
  actions: { public_replies: [''], private_replies: [''], dm_replies: [''] },
  advanced: { require_follow: false, follow_prompt: '', once_per_user: false, cooldown_minutes: 0, active_hours: null, followup: null },
}

export default function RuleForm({ id }) {
  const isNew = id === 'new'
  const [r, setR] = useState(EMPTY)
  const [saved, setSaved] = useState([])
  const [media, setMedia] = useState([])
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.get('/api/saved-replies').then(setSaved).catch(() => {})
    api.get('/api/media').then(setMedia).catch(() => {})
    if (!isNew) api.get('/api/rules').then((rs) => {
      const x = rs.find((y) => String(y.id) === id)
      if (x) setR({
        ...x,
        actions: { public_replies: x.actions.public_replies || [''], private_replies: x.actions.private_replies || [''], dm_replies: x.actions.dm_replies || [''] },
        advanced: { ...EMPTY.advanced, ...x.advanced, cooldown_minutes: Math.round((x.advanced.cooldown_seconds || 0) / 60) },
      })
    })
  }, [id])

  const set = (patch) => setR((x) => ({ ...x, ...patch }))
  const setAdv = (patch) => set({ advanced: { ...r.advanced, ...patch } })
  const setReplies = (k, list) => set({ actions: { ...r.actions, [k]: list } })
  const hasC = r.channels.includes('comment'), hasD = r.channels.includes('dm')

  function toggleChannel(c) {
    set({ channels: r.channels.includes(c) ? r.channels.filter((x) => x !== c) : [...r.channels, c] })
  }

  async function save(e) {
    e.preventDefault(); setBusy(true); setErr('')
    const clean = (l) => l.map((t) => t.trim()).filter(Boolean)
    const adv = { ...r.advanced }
    adv.cooldown_seconds = (Number(adv.cooldown_minutes) || 0) * 60
    delete adv.cooldown_minutes
    if (!adv.require_follow) delete adv.follow_prompt
    if (!adv.followup?.text) delete adv.followup
    if (!adv.active_hours) delete adv.active_hours
    const body = {
      ...r, advanced: adv,
      triggers: r.triggers.filter((t) => t.match === 'any' || t.value.trim()),
      actions: { public_replies: hasC ? clean(r.actions.public_replies) : [], private_replies: hasC ? clean(r.actions.private_replies) : [], dm_replies: hasD ? clean(r.actions.dm_replies) : [] },
    }
    delete body.id; delete body.use_count
    try {
      if (isNew) await api.post('/api/rules', body); else await api.put(`/api/rules/${id}`, body)
      location.hash = '#/channels/instagram/rules'
    } catch (ex) { setErr(ex.message) }
    finally { setBusy(false) }
  }

  async function remove() {
    if (!confirm('این دستور حذف شود؟')) return
    await api.del(`/api/rules/${id}`); location.hash = '#/channels/instagram/rules'
  }

  return (
    <form onSubmit={save}>
      <header className="topbar"><h1>{isNew ? 'دستور جدید' : 'ویرایش دستور'}</h1><a href="#/channels/instagram/rules" className="btn sm">انصراف</a></header>

      <section className="card">
        <div className="field"><label htmlFor="name">نام دستور</label><input id="name" type="text" value={r.name} onChange={(e) => set({ name: e.target.value })} required /></div>
        <div className="field">
          <label>محل دریافت پیام</label>
          <label className="check"><input type="checkbox" checked={hasC} onChange={() => toggleChannel('comment')} /> کامنت پست</label>
          <label className="check"><input type="checkbox" checked={hasD} onChange={() => toggleChannel('dm')} /> دایرکت</label>
        </div>
      </section>

      <section className="card">
        <h2>عبارت شروع پاسخ</h2>
        <p className="hint muted">اگر یکی از شرط‌ها درست باشد، دستور اجرا می‌شود. «هر مقداری» یعنی هر متنی.</p>
        {r.triggers.map((t, i) => (
          <React.Fragment key={i}>
            {i > 0 && <div className="or">یا</div>}
            <div className="trigger">
              <select value={t.match} onChange={(e) => set({ triggers: r.triggers.map((x, j) => j === i ? { ...x, match: e.target.value } : x) })}>
                <option value="any">هر مقداری</option><option value="exact">برابر دقیق</option><option value="contains">شامل باشد</option>
                <option value="starts_with">با این شروع شود</option><option value="regex">الگو (regex)</option>
              </select>
              <input type="text" value={t.value} disabled={t.match === 'any'} placeholder="مثلاً قیمت"
                onChange={(e) => set({ triggers: r.triggers.map((x, j) => j === i ? { ...x, value: e.target.value } : x) })} />
              <button type="button" className="btn sm" disabled={r.triggers.length === 1} onClick={() => set({ triggers: r.triggers.filter((_, j) => j !== i) })}>✕</button>
            </div>
          </React.Fragment>
        ))}
        <button type="button" className="btn sm" onClick={() => set({ triggers: [...r.triggers, { match: 'exact', value: '' }] })}>+ افزودن شرط بیشتر</button>
      </section>

      <section className="card">
        <h2>پیام‌های پاسخ</h2>
        <p className="hint muted">اگر چند متن بنویسید، به نوبت استفاده می‌شوند تا پاسخ‌ها تکراری نباشند.</p>
        {hasC && <ReplyList label="دایرکت خصوصی به کامنت‌گذار" list={r.actions.private_replies} saved={saved} onChange={(l) => setReplies('private_replies', l)} />}
        {hasC && <ReplyList label="پاسخ عمومی زیر کامنت" list={r.actions.public_replies} saved={saved} onChange={(l) => setReplies('public_replies', l)} />}
        {hasD && <ReplyList label="پاسخ دایرکت" list={r.actions.dm_replies} saved={saved} onChange={(l) => setReplies('dm_replies', l)} />}
      </section>

      <section className="card">
        <details>
          <summary>تنظیمات پیشرفته (اختیاری)</summary>
          <div style={{ marginTop: 10 }}>
            <label className="check"><input type="checkbox" checked={!!r.advanced.require_follow} onChange={(e) => setAdv({ require_follow: e.target.checked })} /> شرط دنبال کردن صفحه</label>
            {r.advanced.require_follow && <div className="field"><input type="text" value={r.advanced.follow_prompt || ''} placeholder="پیام راهنما برای کسی که فالو نکرده" onChange={(e) => setAdv({ follow_prompt: e.target.value })} /></div>}
            <label className="check"><input type="checkbox" checked={!!r.advanced.once_per_user} onChange={(e) => setAdv({ once_per_user: e.target.checked })} /> هر کاربر فقط یک بار پاسخ بگیرد</label>
            <div className="field"><label>فاصله‌ی حداقل بین دو پاسخ به یک نفر (دقیقه)</label><input type="number" min="0" value={r.advanced.cooldown_minutes || 0} onChange={(e) => setAdv({ cooldown_minutes: e.target.value })} /></div>
            <div className="field">
              <label>ساعت فعال (به وقت سرور)</label>
              <div className="actions">
                <input type="number" min="0" max="23" style={{ width: 90 }} placeholder="از" value={r.advanced.active_hours?.[0] ?? ''} onChange={(e) => setAdv({ active_hours: e.target.value === '' ? null : [Number(e.target.value), r.advanced.active_hours?.[1] ?? 23] })} />
                <input type="number" min="0" max="24" style={{ width: 90 }} placeholder="تا" value={r.advanced.active_hours?.[1] ?? ''} onChange={(e) => setAdv({ active_hours: [r.advanced.active_hours?.[0] ?? 0, Number(e.target.value)] })} />
              </div>
            </div>
            <div className="field">
              <label>پیگیری خودکار</label>
              <div className="actions">
                <input type="number" min="0" style={{ width: 120 }} placeholder="بعد از (دقیقه)" value={r.advanced.followup ? Math.round(r.advanced.followup.after_seconds / 60) : ''} onChange={(e) => setAdv({ followup: { ...(r.advanced.followup || { text: '' }), after_seconds: Number(e.target.value) * 60 } })} />
              </div>
              <textarea placeholder="متن پیگیری (دایرکت)" value={r.advanced.followup?.text || ''} onChange={(e) => setAdv({ followup: { ...(r.advanced.followup || { after_seconds: 3600 }), text: e.target.value } })} />
              <p className="hint muted">فقط اگر کاربر در دایرکت پیام داده باشد و پنجره‌ی ۲۴ ساعت باز باشد می‌رسد.</p>
            </div>
            {hasC && (
              <div className="field">
                <label>محدود به پست</label>
                <label className="check"><input type="radio" checked={r.post_scope === 'all'} onChange={() => set({ post_scope: 'all' })} /> همه‌ی پست‌ها</label>
                <label className="check"><input type="radio" checked={r.post_scope !== 'all'} onChange={() => set({ post_scope: [] })} /> فقط پست‌های انتخاب‌شده</label>
                {r.post_scope !== 'all' && (
                  <div className="media-pick">
                    {!media.length && <span className="muted">فهرست پست‌ها در دسترس نیست</span>}
                    {media.map((m) => (
                      <label key={m.id}>
                        <input type="checkbox" checked={r.post_scope.includes(m.id)} onChange={(e) => set({ post_scope: e.target.checked ? [...r.post_scope, m.id] : r.post_scope.filter((x) => x !== m.id) })} />
                        {(m.thumbnail_url || m.media_url) && <img src={m.thumbnail_url || m.media_url} alt="" />}
                        <span>{(m.caption || m.id).slice(0, 60)}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            )}
            <div className="field"><label>اولویت (عدد کوچک‌تر زودتر بررسی می‌شود)</label><input type="number" value={r.priority} onChange={(e) => set({ priority: Number(e.target.value) })} /></div>
          </div>
        </details>
      </section>

      {err && <p className="err">{err}</p>}
      <div className="actions">
        <button className="btn primary" disabled={busy}>{isNew ? 'ایجاد و فعال‌سازی' : 'ذخیره'}</button>
        {!isNew && <button type="button" className="btn danger" onClick={remove}>حذف</button>}
      </div>
    </form>
  )
}

function ReplyList({ label, list, saved, onChange }) {
  const [pick, setPick] = useState('')
  return (
    <div className="field">
      <label>{label}</label>
      {list.map((t, i) => (
        <div className="replyline" key={i}>
          <textarea value={t} onChange={(e) => onChange(list.map((x, j) => j === i ? e.target.value : x))} />
          <button type="button" className="btn sm" disabled={list.length === 1} onClick={() => onChange(list.filter((_, j) => j !== i))}>✕</button>
        </div>
      ))}
      <div className="actions">
        <button type="button" className="btn sm" onClick={() => onChange([...list, ''])}>+ پیام جدید</button>
        {saved.length > 0 && (
          <select value={pick} onChange={(e) => { if (e.target.value) onChange([...list.filter(Boolean), e.target.value]); setPick('') }} style={{ width: 'auto' }}>
            <option value="">انتخاب از پیام‌های قبلی…</option>
            {saved.map((s) => <option key={s} value={s}>{s.slice(0, 50)}</option>)}
          </select>
        )}
      </div>
    </div>
  )
}
