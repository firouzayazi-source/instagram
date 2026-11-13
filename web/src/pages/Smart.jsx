import React, { useEffect, useState } from 'react'
import { api, fa } from '../api.js'
import Icon from '../icons.jsx'
import { Products } from './Ai.jsx'
import { Switch } from './Rules.jsx'

// زیربخش‌های پاسخ هوشمند؛ «دستورها» همان صفحه‌ی ‎#/rules‎ است
export const SMART_TABS = [
  ['rules', 'دستورها', 'bot', '#/rules'],
  ['forms', 'فرم‌ساز', 'edit', '#/smart/forms'],
  ['menu', 'منوی ثابت', 'grid', '#/smart/menu'],
  ['faq', 'سؤال‌های متداول', 'msg', '#/smart/faq'],
  ['products', 'محصولات و خدمات', 'cart', '#/smart/products'],
  ['phones', 'خروجی شماره‌ها', 'users', '#/smart/phones'],
]

export function SmartTabs({ cur }) {
  return (
    <div className="chips" style={{ marginTop: 4 }}>
      {SMART_TABS.map(([k, l, ic, href]) => (
        <a key={k} href={href} className={`chip ${cur === k ? 'active' : ''}`}>
          <span style={{ width: 16, height: 16, display: 'inline-flex' }}><Icon n={ic} /></span>{l}
        </a>
      ))}
    </div>
  )
}

const faDay = (ts) => new Date(ts * 1000).toLocaleDateString('fa-IR', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Asia/Tehran' })
const faTime = (ts) => new Date(ts * 1000).toLocaleString('fa-IR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Tehran' })

// فایل CSV با BOM تا اکسل فارسی را درست نشان دهد
function downloadCsv(name, rows) {
  const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const blob = new Blob(['﻿' + rows.map((r) => r.map(esc).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}

export default function Smart({ sub, id }) {
  const cur = SMART_TABS.find(([k]) => k === sub) ? sub : 'forms'
  return (
    <>
      <header className="topbar">
        <div className="title"><h1>پاسخ هوشمند</h1><span className="sub">{SMART_TABS.find(([k]) => k === cur)[1]}</span></div>
        <a href="#/more" className="iconbtn" aria-label="بیشتر"><Icon n="gear" /></a>
      </header>
      <SmartTabs cur={cur} />
      {cur === 'forms' && (id === 'new' || /^\d+$/.test(id || '') ? <FormEdit id={id} /> : id?.startsWith('e') ? <Entries id={id.slice(1)} /> : <Forms />)}
      {cur === 'menu' && <Menu />}
      {cur === 'faq' && <Faq />}
      {cur === 'products' && <Products />}
      {cur === 'phones' && <Phones />}
    </>
  )
}

// ---------- فرم‌ساز ----------

const KINDS = [['text', 'متن'], ['phone', 'شماره موبایل'], ['number', 'عدد'], ['choice', 'گزینه‌ای (دکمه)']]

function Forms() {
  const [items, setItems] = useState(null)
  const load = () => api.get('/api/forms').then(setItems).catch(() => setItems([]))
  useEffect(() => { load() }, [])
  async function toggle(f, on) { await api.put(`/api/forms/${f.id}`, { ...f, enabled: on }); load() }
  async function remove(f) {
    if (!confirm(`فرم «${f.name}» حذف شود؟ جواب‌های ثبت‌شده‌اش هم دیگر دیده نمی‌شوند.`)) return
    try { await api.del(`/api/forms/${f.id}`); load() } catch (ex) { alert(ex.message) }
  }
  return (
    <section className="sec">
      <div className="sec-h"><div className="grow"><h2>فرم‌ها</h2><p>چند سؤال پشت‌سرهم در دایرکت (اسم، شماره، مدل گوشی…). فرم را یک دستور شروع می‌کند: در فرم دستور ← تنظیمات پیشرفته ← «شروع فرم».</p></div></div>
      <div className="sec-b"><a href="#/smart/forms/new" className="btn primary big block"><Icon n="plus" /> فرم جدید</a></div>
      {items === null && <div className="empty">در حال بارگذاری…</div>}
      {items && !items.length && <div className="empty">هنوز فرمی ندارید. مثلاً «مشاوره‌ی خرید»: اسم، شماره، بودجه، نقد یا قسط.</div>}
      <div style={{ borderTop: items?.length ? '1px solid var(--line)' : 0 }}>
        {(items || []).map((f) => (
          <div key={f.id} className="rule" style={f.enabled ? undefined : { opacity: 0.6 }}>
            <div className="rh"><b>{f.name}</b><Switch checked={f.enabled} onChange={(on) => toggle(f, on)} label="فعال" /></div>
            <small className="muted">{fa(f.questions.length)} سؤال: {f.questions.map((q) => q.label).join(' · ')}</small>
            <div className="actions" style={{ marginTop: 4 }}>
              <a href={`#/smart/forms/e${f.id}`} className="btn sm"><Icon n="users" /> جواب‌ها ({fa(f.entries)})</a>
              <a href={`#/smart/forms/${f.id}`} className="btn sm"><Icon n="edit" /> ویرایش</a>
              <button type="button" className="iconbtn" style={{ width: 36, height: 36 }} aria-label="حذف" onClick={() => remove(f)}><Icon n="trash" /></button>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

const EMPTY_FORM = { name: '', enabled: true, done_text: '', questions: [{ label: '', kind: 'text' }] }

function FormEdit({ id }) {
  const isNew = id === 'new'
  const [f, setF] = useState(isNew ? EMPTY_FORM : null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (!isNew) api.get('/api/forms').then((xs) => setF(xs.find((x) => String(x.id) === id) || EMPTY_FORM)).catch(() => setF(EMPTY_FORM))
  }, [id])
  if (!f) return <div className="empty">در حال بارگذاری…</div>
  const setQ = (i, patch) => setF({ ...f, questions: f.questions.map((q, j) => (j === i ? { ...q, ...patch } : q)) })
  const move = (i, d) => {
    const qs = [...f.questions]; const j = i + d
    if (j < 0 || j >= qs.length) return
    ;[qs[i], qs[j]] = [qs[j], qs[i]]
    setF({ ...f, questions: qs })
  }

  async function save(e) {
    e.preventDefault(); setErr(''); setBusy(true)
    const body = { ...f, questions: f.questions.filter((q) => q.label.trim()).map((q) => ({ ...q, options: q.kind === 'choice' ? (q.options || []).map((o) => o.trim()).filter(Boolean) : undefined })) }
    try {
      if (isNew) await api.post('/api/forms', body); else await api.put(`/api/forms/${id}`, body)
      location.hash = '#/smart/forms'
    } catch (ex) { setErr(ex.message) } finally { setBusy(false) }
  }

  return (
    <form onSubmit={save}>
      <section className="sec">
        <div className="sec-h"><span className="ico"><Icon n="edit" /></span><div className="grow"><h2>{isNew ? 'فرم جدید' : 'ویرایش فرم'}</h2></div>
          <Switch checked={f.enabled} onChange={(on) => setF({ ...f, enabled: on })} label="فعال" /></div>
        <div className="sec-b top">
          <div className="field"><label>نام فرم (فقط برای خودتان)</label><input type="text" value={f.name} placeholder="مثلاً: مشاوره‌ی خرید" onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
        </div>
      </section>

      <section className="sec">
        <div className="sec-h"><span className="ico"><Icon n="msg" /></span><div className="grow"><h2>سؤال‌ها</h2><p>به همین ترتیب یکی‌یکی پرسیده می‌شوند. مشتری با نوشتن «لغو» فرم را می‌بندد.</p></div></div>
        <div className="sec-b top">
          {f.questions.map((q, i) => (
            <div key={i} className="sub-card">
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <b className="grow">سؤال {fa(i + 1)}</b>
                <button type="button" className="iconbtn" style={{ width: 32, height: 32 }} aria-label="بالا" onClick={() => move(i, -1)}><Icon n="up" /></button>
                <button type="button" className="iconbtn" style={{ width: 32, height: 32 }} aria-label="پایین" onClick={() => move(i, 1)}><Icon n="down" /></button>
                <button type="button" className="iconbtn" style={{ width: 32, height: 32 }} aria-label="حذف" onClick={() => setF({ ...f, questions: f.questions.filter((_, j) => j !== i) })}><Icon n="trash" /></button>
              </div>
              <textarea rows={2} value={q.label} placeholder="مثلاً: لطفاً شماره‌ی موبایلتون رو بنویسید" onChange={(e) => setQ(i, { label: e.target.value })} />
              <select value={q.kind} onChange={(e) => setQ(i, { kind: e.target.value })}>
                {KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
              {q.kind === 'phone' && <small className="muted">فقط شماره‌ی موبایل درست پذیرفته می‌شود و در پرونده‌ی مشتری هم می‌نشیند.</small>}
              {q.kind === 'choice' && (
                <div className="field"><label>گزینه‌ها (هر خط یکی، حداکثر ۱۳، هر کدام تا ۲۰ نویسه)</label>
                  <textarea rows={3} value={(q.options || []).join('\n')} placeholder={'نقدی\nاقساطی'} onChange={(e) => setQ(i, { options: e.target.value.split('\n') })} /></div>
              )}
            </div>
          ))}
          {f.questions.length < 10 && <button type="button" className="btn block" onClick={() => setF({ ...f, questions: [...f.questions, { label: '', kind: 'text' }] })}><Icon n="plus" /> سؤال جدید</button>}
        </div>
      </section>

      <section className="sec">
        <div className="sec-h"><span className="ico"><Icon n="check" /></span><div className="grow"><h2>پیام پایان</h2><p>بعد از آخرین جواب فرستاده می‌شود. خالی = «ممنون، اطلاعاتتون ثبت شد…»</p></div></div>
        <div className="sec-b top"><textarea rows={3} value={f.done_text} placeholder="ممنون 🌸 همکارانمون به‌زودی تماس می‌گیرن. برای قیمت لحظه‌ای: https://t.me/Poshtibani_stland_bot" onChange={(e) => setF({ ...f, done_text: e.target.value })} /></div>
      </section>

      {err && <p className="err">{err}</p>}
      <div className="actions" style={{ marginBottom: 16 }}>
        <button className="btn primary big" style={{ flex: 1 }} disabled={busy}><Icon n="save" /> ذخیره</button>
        <a href="#/smart/forms" className="btn big">انصراف</a>
      </div>
    </form>
  )
}

function Entries({ id }) {
  const [d, setD] = useState(null)
  useEffect(() => { api.get(`/api/forms/${id}/entries`).then(setD).catch((ex) => setD({ error: ex.message })) }, [id])
  if (!d) return <div className="empty">در حال بارگذاری…</div>
  if (d.error) return <div className="empty err">{d.error}</div>
  const labels = d.form.questions.map((q) => q.label)
  function csv() {
    downloadCsv(`form-${id}.csv`, [['تاریخ', 'نام کاربری', ...labels],
      ...d.items.map((e) => [faTime(e.created_at), e.username ? `@${e.username}` : '', ...labels.map((l) => (e.answers.find((a) => a.label === l) || {}).value || '')])])
  }
  return (
    <section className="sec">
      <div className="sec-h"><div className="grow"><h2>جواب‌های «{d.form.name}»</h2><p>{fa(d.items.length)} فرم کامل</p></div>
        {d.items.length > 0 && <button type="button" className="btn sm" onClick={csv}><Icon n="down" /> اکسل</button>}</div>
      {!d.items.length && <div className="empty">هنوز کسی این فرم را کامل نکرده.</div>}
      <div style={{ borderTop: d.items.length ? '1px solid var(--line)' : 0 }}>
        {d.items.map((e) => (
          <div key={e.id} className="rule">
            <div className="rh"><b>{e.username ? `@${e.username}` : 'کاربر اینستاگرام'}</b><small className="muted">{faTime(e.created_at)}</small></div>
            {e.answers.map((a, i) => (
              <small key={i}><span className="muted">{a.label}:</span> {a.kind === 'phone' ? <a href={`tel:${a.value}`} dir="ltr">{a.value}</a> : a.value}</small>
            ))}
            <div className="actions"><a href={`#/messages/${e.user_id}`} className="btn sm"><Icon n="dm" /> گفتگو</a></div>
          </div>
        ))}
      </div>
      <div className="sec-b"><a href="#/smart/forms" className="btn block">بازگشت به فرم‌ها</a></div>
    </section>
  )
}

// ---------- منوی ثابت ----------

function Menu() {
  const [items, setItems] = useState(null)
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { api.get('/api/dm-menu').then((d) => setItems(d.items)).catch(() => setItems([])) }, [])
  if (!items) return <div className="empty">در حال بارگذاری…</div>
  const setI = (i, patch) => setItems(items.map((x, j) => (j === i ? { ...x, ...patch } : x)))
  async function apply() {
    setMsg(null); setBusy(true)
    try { const d = await api.post('/api/dm-menu', { items }); setItems(d.items); setMsg({ ok: true, text: 'در اینستاگرام ثبت شد ✅ (ممکن است چند دقیقه طول بکشد تا در دایرکت دیده شود)' }) }
    catch (ex) { setMsg({ ok: false, text: ex.message }) } finally { setBusy(false) }
  }
  return (
    <section className="sec">
      <div className="sec-h"><span className="ico"><Icon n="grid" /></span><div className="grow"><h2>منوی ثابت دایرکت</h2>
        <p>دکمه‌هایی که همیشه کنار نوار نوشتن دایرکت پیج دیده می‌شوند. هر دکمه یا لینکی باز می‌کند، یا یک متن آماده جواب می‌دهد (حتی وقتی جواب خودکار دایرکت خاموش است).</p></div></div>
      <div className="sec-b top">
        {items.map((x, i) => (
          <div key={i} className="sub-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <b className="grow">دکمه‌ی {fa(i + 1)}</b>
              <button type="button" className="iconbtn" style={{ width: 32, height: 32 }} aria-label="حذف" onClick={() => setItems(items.filter((_, j) => j !== i))}><Icon n="trash" /></button>
            </div>
            <input type="text" maxLength={30} value={x.title} placeholder="عنوان دکمه، مثلاً: 🤖 ربات پشتیبان" onChange={(e) => setI(i, { title: e.target.value })} />
            <div className="chips" style={{ margin: 0 }}>
              <button type="button" className={`chip ${x.type === 'url' ? 'active' : ''}`} onClick={() => setI(i, { type: 'url' })}>باز کردن لینک</button>
              <button type="button" className={`chip ${x.type !== 'url' ? 'active' : ''}`} onClick={() => setI(i, { type: 'text' })}>فرستادن متن</button>
            </div>
            {x.type === 'url'
              ? <input type="url" dir="ltr" value={x.value} placeholder="https://t.me/Poshtibani_stland_bot" onChange={(e) => setI(i, { value: e.target.value })} />
              : <textarea rows={3} value={x.value} placeholder="متنی که با لمس این دکمه فرستاده می‌شود" onChange={(e) => setI(i, { value: e.target.value })} />}
          </div>
        ))}
        {items.length < 5 && <button type="button" className="btn block" onClick={() => setItems([...items, { title: '', type: 'url', value: '' }])}><Icon n="plus" /> دکمه‌ی جدید</button>}
        <div className="note info">هنوز از راه اتصال فعلی (Composio) روی پیج آزموده نشده؛ اگر اینستاگرام قبول نکند، پیام خطا همین‌جا نشان داده می‌شود و منو فقط در پنل ذخیره می‌ماند.</div>
        {msg && <p className={msg.ok ? 'ok' : 'err'}>{msg.text}</p>}
        <button type="button" className="btn primary big block" disabled={busy} onClick={apply}><Icon n="save" /> ذخیره و ثبت در اینستاگرام</button>
      </div>
    </section>
  )
}

// ---------- سؤال‌های متداول (شروع گفتگو) ----------

function Faq() {
  const [qs, setQs] = useState(null)
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { api.get('/api/ai/settings').then((r) => setQs(r.settings.ice_breakers || [])).catch(() => setQs([])) }, [])
  if (!qs) return <div className="empty">در حال بارگذاری…</div>
  async function apply() {
    setMsg(null); setBusy(true)
    try { const d = await api.post('/api/instagram/ice-breakers', { questions: qs.map((x) => x.trim()).filter(Boolean) }); setQs(d.questions); setMsg({ ok: true, text: 'در اینستاگرام ثبت شد ✅' }) }
    catch (ex) { setMsg({ ok: ex.status === 409, text: ex.message }) } finally { setBusy(false) }
  }
  return (
    <section className="sec">
      <div className="sec-h"><span className="ico"><Icon n="msg" /></span><div className="grow"><h2>سؤال‌های متداول</h2>
        <p>وقتی کسی برای اولین بار دایرکت پیج را باز می‌کند، این سؤال‌ها (حداکثر ۴) را می‌بیند و با یک لمس می‌پرسد. جوابش را دستورها یا مغز مرکزی می‌دهد.</p></div></div>
      <div className="sec-b top">
        {qs.map((q, i) => (
          <div key={i} style={{ display: 'flex', gap: 6 }}>
            <input type="text" maxLength={80} value={q} placeholder="مثلاً: شرایط اقساط چطوره؟" onChange={(e) => setQs(qs.map((x, j) => (j === i ? e.target.value : x)))} />
            <button type="button" className="iconbtn" style={{ width: 44, flex: 'none' }} aria-label="حذف" onClick={() => setQs(qs.filter((_, j) => j !== i))}><Icon n="trash" /></button>
          </div>
        ))}
        {qs.length < 4 && <button type="button" className="btn block" onClick={() => setQs([...qs, ''])}><Icon n="plus" /> سؤال جدید</button>}
        <div className="note info">برای اینکه به هر سؤال جواب مشخصی برود، یک دستور دایرکت با «برابر دقیق» همان متن بسازید.</div>
        {msg && <p className={msg.ok ? 'ok' : 'err'}>{msg.text}</p>}
        <button type="button" className="btn primary big block" disabled={busy} onClick={apply}><Icon n="save" /> ذخیره و ثبت در اینستاگرام</button>
      </div>
    </section>
  )
}

// ---------- خروجی شماره‌ها ----------

const RANGES = [[0, 'همه'], [1, 'امروز'], [7, '۷ روز'], [30, '۳۰ روز'], [90, '۹۰ روز']]
const intl = (p) => '98' + String(p).replace(/^0/, '')

function Phones() {
  const [items, setItems] = useState(null)
  const [q, setQ] = useState('')
  const [days, setDays] = useState(0)
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    const t = setTimeout(() => {
      const since = days ? Math.floor(Date.now() / 1000) - days * 86400 : 0
      api.get(`/api/phones?q=${encodeURIComponent(q.trim())}&since=${since}`).then(setItems).catch(() => setItems([]))
    }, 300)
    return () => clearTimeout(t)
  }, [q, days])
  function csv() {
    downloadCsv('phones.csv', [['شماره', 'نام', 'نام کاربری', 'کانال', 'برچسب‌ها', 'اولین تماس', 'آخرین تماس'],
      ...items.map((r) => [r.phone, r.name, r.username ? `@${r.username}` : '', r.channel === 'ig' ? 'اینستاگرام' : r.channel, r.tags.join('، '), faDay(r.first_seen), faDay(r.last_seen)])])
  }
  async function copyAll() {
    try { await navigator.clipboard.writeText(items.map((r) => r.phone).join('\n')); setCopied(true); setTimeout(() => setCopied(false), 2000) } catch { /* مرورگر اجازه نداد */ }
  }
  return (
    <section className="sec">
      <div className="sec-h"><span className="ico"><Icon n="users" /></span><div className="grow"><h2>خروجی شماره‌ها</h2>
        <p>شماره‌هایی که مشتری‌ها در دایرکت، کامنت یا فرم نوشته‌اند (یا شما در پرونده ثبت کرده‌اید). فقط برای تماس خودتان؛ جایی منتشرش نکنید.</p></div></div>
      <div className="sec-b">
        <input type="text" value={q} placeholder="جستجو در نام، نام کاربری یا شماره" onChange={(e) => setQ(e.target.value)} />
        <div className="chips" style={{ margin: 0 }}>
          {RANGES.map(([d, l]) => <button key={d} type="button" className={`chip ${days === d ? 'active' : ''}`} onClick={() => setDays(d)}>{l}</button>)}
        </div>
        {items && items.length > 0 && (
          <div className="actions">
            <button type="button" className="btn sm" onClick={csv}><Icon n="down" /> خروجی اکسل ({fa(items.length)})</button>
            <button type="button" className="btn sm" onClick={copyAll}><Icon n="copy" /> {copied ? 'کپی شد ✅' : 'کپی همه‌ی شماره‌ها'}</button>
          </div>
        )}
      </div>
      {items === null && <div className="empty">در حال بارگذاری…</div>}
      {items && !items.length && <div className="empty">شماره‌ای در این بازه پیدا نشد.</div>}
      <div style={{ borderTop: items?.length ? '1px solid var(--line)' : 0 }}>
        {(items || []).map((r) => (
          <div key={r.key} className="rule">
            <div className="rh">
              <b>{r.name || (r.username ? `@${r.username}` : 'بدون نام')}</b>
              <a href={`tel:${r.phone}`} dir="ltr" style={{ fontVariantNumeric: 'tabular-nums' }}>{r.phone}</a>
            </div>
            <small className="muted">{r.username && r.name ? `@${r.username} · ` : ''}آخرین تماس {faDay(r.last_seen)}{r.tags.length ? ` · ${r.tags.join('، ')}` : ''}</small>
            <div className="actions">
              <a href={`tel:${r.phone}`} className="btn sm">تماس</a>
              <a href={`https://wa.me/${intl(r.phone)}`} target="_blank" rel="noreferrer" className="btn sm">واتساپ</a>
              <a href={`https://t.me/+${intl(r.phone)}`} target="_blank" rel="noreferrer" className="btn sm">تلگرام</a>
              <a href={`#/customers/${r.key}`} className="btn sm"><Icon n="user" /> پرونده</a>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
