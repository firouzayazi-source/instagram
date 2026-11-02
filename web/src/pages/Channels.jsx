import React, { useEffect, useState } from 'react'
import { api, fa, timeAgo } from '../api.js'
import Rules from './Rules.jsx'
import { Blocked, Msg } from './Ai.jsx'

// هر کانال قابلیت‌های خودش را دارد؛ هسته‌ی مرکزی (مغز، دانش، هوش مصنوعی) مشترک است
const SUBS = {
  instagram: [['connect', 'اتصال و وضعیت'], ['dm', 'دایرکت'], ['comment', 'کامنت'], ['rules', 'دستورها'], ['blocked', 'مسدودها']],
  telegram: [['connect', 'اتصال و وضعیت']],
}

function statusOf(c) {
  if (!c.ready) return ['muted', 'به‌زودی']
  if (!c.enabled) return ['muted', 'خاموش']
  if (c.connected) return ['good', 'متصل']
  return ['warn', 'نیاز به اتصال']
}

export function ChannelList() {
  const [items, setItems] = useState(null)
  const [msg, setMsg] = useState(null)
  const load = () => api.get('/api/channels').then(setItems).catch(() => {})
  useEffect(() => { load() }, [])

  async function toggle(c) {
    const off = c.enabled
    if (off && !confirm(`«${c.label}» خاموش شود؟ پیام‌ها دیگر جواب خودکار نمی‌گیرند (در اینستاگرام در صندوق ثبت می‌شوند).`)) return
    try { await api.put(`/api/channels/${c.id}`, { enabled: !off }); setMsg({ ok: true, text: `«${c.label}» ${off ? 'خاموش' : 'روشن'} شد` }); load() }
    catch (ex) { setMsg({ ok: false, text: ex.message }) }
  }

  if (!items) return <div className="empty">در حال بارگذاری…</div>
  return (
    <>
      <Msg m={msg} />
      <div className="list">
        {items.map((c) => {
          const [cls, label] = statusOf(c)
          return (
            <div key={c.id} className={`item ${c.ready ? '' : 'disabled'}`} style={{ cursor: 'default' }}>
              <div className="row">
                <span className="who">{c.label} <span className={`pill ${cls}`}>{label}</span></span>
                {c.ready
                  ? <label className="switch"><input type="checkbox" checked={c.enabled} onChange={() => toggle(c)} /><span /></label>
                  : null}
              </div>
              {c.ready && (
                <div className="row" style={{ marginTop: 4 }}>
                  <span className="muted">{c.enabled && !c.connected ? c.note : (c.id === 'telegram' && c.username ? `@${c.username}` : '')}</span>
                  <a className="btn sm" href={`#/channels/${c.id}/connect`}>مدیریت</a>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </>
  )
}

function Connect({ id }) {
  const [c, setC] = useState(null)
  useEffect(() => { api.get('/api/channels').then((xs) => setC(xs.find((x) => x.id === id))).catch(() => {}) }, [id])
  if (!c) return <div className="empty">در حال بارگذاری…</div>
  const [cls, label] = statusOf(c)
  return (
    <>
      <section className="card">
        <div className="row-between"><h2 style={{ margin: 0 }}>{c.label}</h2><span className={`pill ${cls}`}>{label}</span></div>
        {c.note && <p className={c.enabled ? 'err' : 'muted'}>{c.note}</p>}
        {id === 'instagram' && (
          <div className="tiles" style={{ marginTop: 10 }}>
            <div className="tile"><b>{fa(c.events_24h)}</b><span>رویداد ۲۴ ساعت</span></div>
            <div className="tile"><b>{c.last_event ? timeAgo(c.last_event) : '—'}</b><span>آخرین رویداد</span></div>
            <div className={`tile ${c.token_days_left !== null && c.token_days_left < 10 ? 'warn' : ''}`}><b>{c.token_days_left === null ? '—' : fa(c.token_days_left)}</b><span>روز تا انقضای توکن</span></div>
          </div>
        )}
        {id === 'telegram' && (
          <div className="tiles" style={{ marginTop: 10 }}>
            <div className={`tile ${c.online ? 'good' : 'warn'}`}><b>{c.online ? 'آنلاین' : 'بی‌خبر'}</b><span>ربات</span></div>
            <div className="tile"><b>{c.users === null || c.users === undefined ? '—' : fa(c.users)}</b><span>کاربر</span></div>
            <div className="tile"><b>{c.last_seen ? timeAgo(c.last_seen) : '—'}</b><span>آخرین گزارش</span></div>
          </div>
        )}
      </section>

      <section className="card">
        <h2>اطلاعات اتصال</h2>
        <div className="list">
          {c.fields.map((f) => (
            <div key={f.key} className="row" style={{ padding: '6px 0' }}>
              <span>{f.label} <span className="muted" dir="ltr">({f.key})</span></span>
              <span className={`pill ${f.set ? 'good' : 'warn'}`}>{f.set ? 'تنظیم شده' : 'خالی'}</span>
            </div>
          ))}
        </div>
        <p className="hint muted">مقدارها روی سرور در ‎/opt/igbot/.env هستند و هیچ‌وقت در پنل نمایش داده نمی‌شوند. بعد از تغییر: <span dir="ltr">systemctl restart {id === 'telegram' ? 'igbot-telegram' : 'igbot'}</span></p>
        {id === 'instagram' && <p className="hint muted">آدرس وبهوک در اپ متا: <b dir="ltr">{c.webhook_url}</b> · فیلدها: comments و messages. راهنمای کامل در docs/META_SETUP.md</p>}
      </section>

      {id === 'telegram' && <TgAi />}
      {id === 'telegram' && (
        <section className="card">
          <h2>تنظیمات تلگرام</h2>
          <p className="muted">پرسش‌ها، جواب‌ها و متن‌های پایه (آدرس، اقساط…) از «مغز مرکزی ← دانش مرکزی» می‌آیند و برای همه‌ی کانال‌ها یکی‌اند.</p>
          <p className="muted">منوی ربات، بنرها، گروه پشتیبانی با تاپیک، حالت همکار، پیام همگانی و مشاور خرید مخصوص تلگرام‌اند و از پنل داخل خود ربات مدیریت می‌شوند: در تلگرام به ربات <b dir="ltr">/admin</b> بفرستید.</p>
          {c.username && <a className="btn" href={`https://t.me/${c.username}`} target="_blank" rel="noreferrer">باز کردن ربات در تلگرام</a>}
        </section>
      )}
    </>
  )
}

function TgAi() {
  const [s, setS] = useState(null)
  const [msg, setMsg] = useState(null)
  useEffect(() => { api.get('/api/ai/settings').then((r) => setS(r.settings)).catch(() => {}) }, [])
  if (!s) return null
  async function toggle(v) {
    try { const r = await api.put('/api/ai/settings', { telegram_ai: v }); setS(r.settings); setMsg({ ok: true, text: 'ذخیره شد ✅' }) }
    catch (ex) { setMsg({ ok: false, text: ex.message }) }
  }
  return (
    <section className="card">
      <h2>هوش مصنوعی در تلگرام</h2>
      <label className="check"><input type="checkbox" checked={s.telegram_ai} onChange={(e) => toggle(e.target.checked)} /> وقتی موتور فهم پیامی را نفهمید، هوش مصنوعی مرکزی جواب بدهد</label>
      <p className="hint muted">همان کلید، مدل، بودجه، دانش و لاگ «مغز مرکزی». {s.enabled ? 'هوش مصنوعی مرکزی روشن است.' : 'هوش مصنوعی مرکزی الان خاموش است؛ تا روشن نشود، ربات مثل قبل از مشتری می‌خواهد بازتر بنویسد یا به همکار می‌سپارد.'} اگر جواب کامل نداشته باشد، پیام به گروه پشتیبانی می‌رود.</p>
      <Msg m={msg} />
    </section>
  )
}

function IgPart({ part }) {
  const [s, setS] = useState(null)
  const [msg, setMsg] = useState(null)
  useEffect(() => { api.get('/api/ai/settings').then((r) => setS(r.settings)).catch(() => {}) }, [])
  if (!s) return <div className="empty">در حال بارگذاری…</div>
  const set = (patch) => setS({ ...s, ...patch })
  const KEYS = part === 'dm' ? ['dm_enabled', 'prompt_dm'] : ['comment_enabled', 'comment_mode', 'public_ack', 'public_prices', 'prompt_comment']

  async function save(e) {
    e.preventDefault(); setMsg(null)
    try {
      const r = await api.put('/api/ai/settings', Object.fromEntries(KEYS.map((k) => [k, s[k]])))
      setS(r.settings); setMsg({ ok: true, text: 'ذخیره شد ✅' })
    } catch (ex) { setMsg({ ok: false, text: ex.message }) }
  }

  return (
    <form onSubmit={save}>
      {part === 'dm' && (
        <section className="card">
          <h2>پاسخ خودکار دایرکت</h2>
          <label className="check"><input type="checkbox" checked={s.dm_enabled} onChange={(e) => set({ dm_enabled: e.target.checked })} /> مغز مرکزی به دایرکت‌های اینستاگرام جواب بدهد</label>
          <p className="hint muted">دستورهای کلمه‌ای (تب «دستورها») همیشه اول بررسی می‌شوند؛ اگر هیچ‌کدام نخورد، نوبت مغز مرکزی است.</p>
          <div className="field">
            <label>دستورالعمل اختصاصی دایرکت (اختیاری، برای هوش مصنوعی)</label>
            <textarea value={s.prompt_dm} placeholder="مثلاً: همیشه آخر پیام بپرس مدل گوشی فعلی‌اش چیست." onChange={(e) => set({ prompt_dm: e.target.value })} />
          </div>
        </section>
      )}
      {part === 'comment' && (
        <section className="card">
          <h2>پاسخ خودکار کامنت</h2>
          <label className="check"><input type="checkbox" checked={s.comment_enabled} onChange={(e) => set({ comment_enabled: e.target.checked })} /> مغز مرکزی به کامنت‌ها جواب بدهد</label>
          <label className="check"><input type="radio" checked={s.comment_mode === 'dm_and_public'} onChange={() => set({ comment_mode: 'dm_and_public' })} /> جواب کامل در دایرکت خصوصی، و یک متن کوتاه عمومی زیر کامنت (پیشنهادی)</label>
          <label className="check"><input type="radio" checked={s.comment_mode === 'public_only'} onChange={() => set({ comment_mode: 'public_only' })} /> فقط جواب عمومی زیر کامنت</label>
          <label className="check"><input type="checkbox" checked={s.public_prices} onChange={(e) => set({ public_prices: e.target.checked })} /> قیمت را عمومی هم بگوید</label>
          <div className="field">
            <label>متن‌های عمومی زیر کامنت (هر خط یکی، به نوبت)</label>
            <textarea value={(s.public_ack || []).join('\n')} onChange={(e) => set({ public_ack: e.target.value.split('\n') })} />
          </div>
          <div className="field">
            <label>دستورالعمل اختصاصی کامنت (اختیاری، برای هوش مصنوعی)</label>
            <textarea value={s.prompt_comment} placeholder="مثلاً: زیر پست‌های آموزشی فقط تشکر کن." onChange={(e) => set({ prompt_comment: e.target.value })} />
          </div>
        </section>
      )}
      <Msg m={msg} />
      <div className="actions sticky-save"><button className="btn primary">ذخیره</button></div>
    </form>
  )
}

export default function Channels({ id, sub }) {
  if (!id || !SUBS[id]) {
    return (
      <>
        <header className="topbar"><h1>کانال‌ها</h1><span className="sub">هر شبکه جدا روشن و خاموش می‌شود</span></header>
        <p className="muted">همه‌ی کانال‌ها از یک مغز مرکزی و یک دانش جواب می‌دهند؛ هر کانال قابلیت‌ها و تنظیمات خودش را دارد.</p>
        <ChannelList />
      </>
    )
  }
  const subs = SUBS[id]
  const cur = subs.find(([k]) => k === sub) ? sub : 'connect'
  return (
    <>
      <header className="topbar"><h1>{id === 'instagram' ? 'اینستاگرام' : 'تلگرام'}</h1><a href="#/channels" className="btn sm">همه‌ی کانال‌ها</a></header>
      {subs.length > 1 && (
        <div className="chips">
          {subs.map(([k, l]) => <a key={k} href={`#/channels/${id}/${k}`} className={`chip ${cur === k ? 'active' : ''}`}>{l}</a>)}
        </div>
      )}
      {cur === 'connect' && <Connect id={id} />}
      {cur === 'dm' && <IgPart part="dm" />}
      {cur === 'comment' && <IgPart part="comment" />}
      {cur === 'rules' && <Rules embedded />}
      {cur === 'blocked' && <Blocked />}
    </>
  )
}
