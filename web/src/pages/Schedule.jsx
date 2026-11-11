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

// ساعت دیواری تهران ← زمان واقعی، هر جا که مرورگر باشد
function tehranToEpoch(value) {
  return Date.parse(`${value}:00+03:30`) / 1000
}

export default function Schedule() {
  const [items, setItems] = useState([])
  const [f, setF] = useState({ kind: 'reel', caption: '', at: '' })
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
    if (!f.at) return setMsg({ ok: false, text: 'روز و ساعت انتشار را انتخاب کنید' })
    setBusy(true)
    try {
      const body = isVideo ? file : await toJpeg(file)
      const ext = isVideo ? (file.name.toLowerCase().endsWith('.mov') ? 'mov' : 'mp4') : 'jpg'
      const up = await api.upload(`/api/schedule/upload?name=file.${ext}`, body)
      await api.post('/api/schedule', { kind: f.kind, file: up.file, caption: f.caption, publish_at: tehranToEpoch(f.at) })
      setMsg({ ok: true, text: 'در نوبت انتشار گذاشته شد ✅' })
      setFile(null); setF({ ...f, caption: '', at: '' }); if (input.current) input.current.value = ''
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
          <input type="datetime-local" value={f.at} onChange={(e) => setF({ ...f, at: e.target.value })} />
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
