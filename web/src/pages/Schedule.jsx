import React, { useEffect, useRef, useState } from 'react'
import { api, fa } from '../api.js'
import { Msg } from './Ai.jsx'

const KIND = { post: 'پست', reel: 'ریلز', story: 'استوری' }
const STATUS = { scheduled: ['در نوبت', 'warn'], publishing: ['در حال انتشار', 'warn'], done: ['منتشر شد', 'good'], failed: ['ناموفق', 'bad'], canceled: ['لغو شد', ''] }
const when = (ts) => new Date(ts * 1000).toLocaleString('fa-IR', { weekday: 'long', day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Tehran' })

// هر عکسی (PNG، HEIC نمایش‌پذیر…) به JPG تبدیل می‌شود چون اینستاگرام فقط JPG می‌پذیرد
function toJpeg(file) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      const k = Math.min(1, 1440 / img.width)
      const cv = document.createElement('canvas')
      cv.width = Math.round(img.width * k); cv.height = Math.round(img.height * k)
      cv.getContext('2d').drawImage(img, 0, 0, cv.width, cv.height)
      cv.toBlob((b) => (b ? resolve(b) : reject(new Error('تبدیل عکس نشد'))), 'image/jpeg', 0.92)
    }
    img.onerror = () => reject(new Error('این عکس خوانده نشد'))
    img.src = URL.createObjectURL(file)
  })
}

// تاریخ و ساعت تهران (ایران ساعت تابستانی ندارد: همیشه ‎+03:30‎)
const ymdTehran = (ms) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Tehran', year: 'numeric', month: '2-digit', day: '2-digit' }).format(ms)
const hourTehran = (ms) => Number(new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Tehran', hour: '2-digit', hourCycle: 'h23' }).format(ms))
const toEpoch = ({ day, h, m }) => Date.parse(`${day}T${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00+03:30`) / 1000
const pad = (n) => String(n).padStart(2, '0').replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[d])

function days() {
  const out = []
  for (let i = 0; i < 30; i++) {
    const day = ymdTehran(Date.now() + i * 86400000)
    const label = new Date(`${day}T12:00:00+03:30`).toLocaleDateString('fa-IR', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'Asia/Tehran' })
    out.push([day, i === 0 ? `امروز، ${label}` : i === 1 ? `فردا، ${label}` : label])
  }
  return out
}

// پیش‌فرض: ساعت ۲۱ امروز (اوج آنلاین بودن فالوورها)، یا فردا اگر گذشته
function defaultWhen() {
  const late = hourTehran(Date.now()) >= 21
  return { day: ymdTehran(Date.now() + (late ? 86400000 : 0)), h: 21, m: 0 }
}

// انتخاب‌گر شمسی: روز، ساعت، دقیقه
function WhenPicker({ value, onChange }) {
  const set = (patch) => onChange({ ...value, ...patch })
  const now = Date.now()
  return (
    <>
      <div className="actions" style={{ flexWrap: 'nowrap' }}>
        <select value={value.day} onChange={(e) => set({ day: e.target.value })} style={{ flex: 2 }}>
          {days().map(([d, l]) => <option key={d} value={d}>{l}</option>)}
        </select>
        <select value={value.h} onChange={(e) => set({ h: Number(e.target.value) })} style={{ flex: 1 }} aria-label="ساعت">
          {Array.from({ length: 24 }, (_, i) => <option key={i} value={i}>{pad(i)}</option>)}
        </select>
        <select value={value.m} onChange={(e) => set({ m: Number(e.target.value) })} style={{ flex: 1 }} aria-label="دقیقه">
          {Array.from({ length: 12 }, (_, i) => i * 5).map((i) => <option key={i} value={i}>{pad(i)}</option>)}
        </select>
      </div>
      <div className="actions" style={{ marginTop: 6 }}>
        <button type="button" className="chip" onClick={() => { const t = new Date(now + 10 * 60000); onChange({ day: ymdTehran(t), h: hourTehran(t), m: Math.ceil(Number(new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Tehran', minute: '2-digit' }).format(t)) / 5) * 5 % 60 }) }}>۱۰ دقیقه‌ی دیگر</button>
        <button type="button" className="chip" onClick={() => onChange({ day: ymdTehran(now + (hourTehran(now) >= 21 ? 86400000 : 0)), h: 21, m: 0 })}>ساعت ۲۱</button>
      </div>
      <p className="hint muted" style={{ marginTop: 4 }}>
        {toEpoch(value) * 1000 <= now + 60000 ? <span className="err">این زمان گذشته است</span>
          : <>انتشار: {new Date(toEpoch(value) * 1000).toLocaleString('fa-IR', { weekday: 'long', day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Tehran' })}</>}
      </p>
    </>
  )
}

export default function Schedule() {
  const [items, setItems] = useState([])
  const [f, setF] = useState({ kind: 'reel', caption: '', at: defaultWhen() })
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  const input = useRef(null)
  const load = () => api.get('/api/schedule').then(setItems).catch(() => {})
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t) }, [])

  const isVideo = file && file.type.startsWith('video/')
  async function save(e) {
    e.preventDefault(); setMsg(null)
    if (!file) return setMsg({ ok: false, text: 'فایل را انتخاب کنید' })
    setBusy(true)
    try {
      const body = isVideo ? file : await toJpeg(file)
      const ext = isVideo ? (file.name.toLowerCase().endsWith('.mov') ? 'mov' : 'mp4') : 'jpg'
      const up = await api.upload(`/api/schedule/upload?name=file.${ext}`, body)
      await api.post('/api/schedule', { kind: f.kind, file: up.file, caption: f.caption, publish_at: toEpoch(f.at) })
      setMsg({ ok: true, text: 'در نوبت انتشار گذاشته شد ✅' })
      setFile(null); setF({ ...f, caption: '', at: defaultWhen() }); if (input.current) input.current.value = ''
      load()
    } catch (ex) { setMsg({ ok: false, text: ex.message }) }
    setBusy(false)
  }
  async function cancel(x) {
    if (!window.confirm('این انتشار لغو شود؟')) return
    try { await api.post(`/api/schedule/${x.id}/cancel`); load() } catch (ex) { setMsg({ ok: false, text: ex.message }) }
  }

  const waiting = items.filter((x) => x.status === 'scheduled' || x.status === 'publishing')
  const past = items.filter((x) => !waiting.includes(x))
  return (
    <>
      <form className="card" onSubmit={save}>
        <h2>انتشار زمان‌بندی‌شده</h2>
        <p className="muted">فایل و ساعت را خودتان انتخاب می‌کنید؛ همان ساعت روی پیج منتشر می‌شود و خبرش به تلگرام می‌آید. فالوورهای شما بیشتر بین ۲۰:۳۰ تا ۲۳:۳۰ آنلاین‌اند.</p>
        <div className="actions" style={{ marginBottom: 10 }}>
          {Object.entries(KIND).map(([k, v]) => <button type="button" key={k} className={`chip ${f.kind === k ? 'active' : ''}`} onClick={() => setF({ ...f, kind: k })}>{v}</button>)}
        </div>
        <div className="field">
          <label>{f.kind === 'reel' ? 'ویدیو (MP4 یا MOV، عمودی ۹:۱۶)' : f.kind === 'story' ? 'عکس یا ویدیو (عمودی ۹:۱۶)' : 'عکس'}</label>
          <input ref={input} type="file" accept={f.kind === 'reel' ? 'video/mp4,video/quicktime' : f.kind === 'post' ? 'image/*' : 'image/*,video/mp4,video/quicktime'} onChange={(e) => setFile(e.target.files[0] || null)} />
          {file && <p className="hint muted">{file.name} · {fa((file.size / 1048576).toFixed(1))} مگابایت</p>}
        </div>
        {f.kind !== 'story' && (
          <div className="field">
            <label>کپشن</label>
            <textarea rows="4" maxLength="2200" value={f.caption} onChange={(e) => setF({ ...f, caption: e.target.value })} />
          </div>
        )}
        <div className="field">
          <label>روز و ساعت انتشار (به وقت تهران)</label>
          <WhenPicker value={f.at} onChange={(at) => setF({ ...f, at })} />
        </div>
        <button className="btn primary" disabled={busy}>{busy ? 'در حال فرستادن فایل…' : 'بگذار در نوبت'}</button>
        <Msg m={msg} />
        {f.kind === 'story' && <p className="hint muted">استیکر (نظرسنجی، لینک) را فقط خود اپ اینستاگرام می‌تواند بگذارد؛ استوری زمان‌بندی‌شده بدون استیکر منتشر می‌شود.</p>}
      </form>

      <section className="card">
        <h3>در نوبت</h3>
        {!waiting.length ? <div className="empty">چیزی در نوبت نیست.</div> : <List items={waiting} onCancel={cancel} />}
      </section>
      {past.length > 0 && <section className="card"><h3>قبلی‌ها</h3><List items={past} /></section>}
    </>
  )
}

function List({ items, onCancel }) {
  return (
    <div className="list">
      {items.map((x) => {
        const [label, cls] = STATUS[x.status] || [x.status, '']
        return (
          <div key={x.id} className="item" style={{ cursor: 'default' }}>
            <div className="row-between">
              <span>{KIND[x.kind]} · {when(x.publish_at)}</span>
              <span className={`pill ${cls}`}>{label}</span>
            </div>
            {x.caption && <div className="muted" style={{ marginTop: 4 }}>{x.caption.slice(0, 120)}</div>}
            {x.error && <div className="err" style={{ marginTop: 4 }}>{x.error}</div>}
            <div className="actions" style={{ marginTop: 6 }}>
              {x.preview && <a className="btn sm" href={x.preview} target="_blank" rel="noreferrer">دیدن فایل</a>}
              {x.permalink && <a className="btn sm" href={x.permalink} target="_blank" rel="noreferrer">دیدن در اینستاگرام</a>}
              {onCancel && x.status === 'scheduled' && <button className="btn sm" onClick={() => onCancel(x)}>لغو</button>}
            </div>
          </div>
        )
      })}
    </div>
  )
}
