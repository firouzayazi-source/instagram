import React, { useEffect, useMemo, useState } from 'react'
import { api, fa, money, timeAgo, usd } from '../api.js'
import AiAdmin from './AiAdmin.jsx'
import AiKeys from './AiKeys.jsx'

const SUBS = [
  ['overview', 'نمای کلی'],
  ['handoffs', 'ارجاع به شما'],
  ['faq', 'دانش مرکزی'],
  ['admin', 'تنظیم با حرف'],
  ['products', 'محصولات و قیمت'],
  ['docs', 'فایل‌ها'],
  ['settings', 'تنظیمات مغز'],
  ['log', 'لاگ پاسخ‌ها'],
]
// تنظیم‌های مخصوص اینستاگرام که در «کانال‌ها ← اینستاگرام» ویرایش می‌شوند؛ صفحه‌ی مغز مرکزی آن‌ها را نمی‌فرستد
const IG_KEYS = ['human_pause_minutes', 'batch_wait_seconds', 'notify_telegram', 'telegram_ai', 'welcome_text', 'quick_replies_enabled', 'dm_quick_replies', 'typing_indicator', 'ice_breakers', 'mention_reply_enabled', 'mention_replies', 'mod_profanity', 'mod_links', 'mod_words', 'dm_enabled', 'comment_enabled', 'comment_mode', 'public_ack', 'public_prices', 'prompt_dm', 'prompt_comment', 'showcase_cards', 'order_enabled', 'order_payment_text', 'auto_followup_enabled', 'auto_followup_hours', 'auto_followup_text']
const ACTION_FA = { reply: 'پاسخ داد', handoff: 'ارجاع', ignore: 'نادیده', skip: 'رد شد', error: 'خطا' }
const ACTION_CLS = { reply: 'good', handoff: 'warn', ignore: 'muted', skip: 'muted', error: 'bad' }
const SKIP_FA = { emoji: 'فقط ایموجی', budget: 'سقف بودجه', disabled: 'خاموش', channel_disabled: 'کانال خاموش', no_api_key: 'کلید API ندارد' }

export default function Ai({ sub = 'overview', badges = {} }) {
  const cur = SUBS.find(([k]) => k === sub) ? sub : 'overview'
  return (
    <>
      <header className="topbar"><h1>مغز مرکزی</h1><span className="sub">یک مغز و یک دانش برای همه‌ی کانال‌ها</span></header>
      <div className="chips">
        {SUBS.map(([k, l]) => (
          <a key={k} href={`#/ai/${k}`} className={`chip ${cur === k ? 'active' : ''}`}>
            {l}{k === 'handoffs' && badges.handoffs > 0 && <span className="count">{fa(badges.handoffs)}</span>}
          </a>
        ))}
      </div>
      {cur === 'overview' && <Overview />}
      {cur === 'handoffs' && <Handoffs />}
      {cur === 'settings' && <><AiKeys /><Settings /></>}
      {cur === 'faq' && <Kb />}
      {cur === 'admin' && <AiAdmin />}
      {cur === 'products' && <Products />}
      {cur === 'docs' && <Docs />}
      {cur === 'log' && <Log />}
    </>
  )
}

export function Msg({ m }) {
  if (!m) return null
  return <p className={m.ok ? 'ok' : 'err'}>{m.text}</p>
}

// ---------- نمای کلی ----------

function Overview() {
  const [st, setSt] = useState(null)
  const [counts, setCounts] = useState({ faq: 0, products: 0, docs: 0, info: false })
  const [toggling, setToggling] = useState(false)

  const load = () => {
    api.get('/api/ai/stats').then(setSt).catch(() => {})
    Promise.all([api.get('/api/ai/faq'), api.get('/api/ai/products'), api.get('/api/ai/docs'), api.get('/api/ai/settings')])
      .then(([f, p, d, s]) => setCounts({ faq: f.length, products: p.length, docs: d.length, info: !!s.settings.business_info.trim() }))
      .catch(() => {})
  }
  useEffect(load, [])

  async function toggle() {
    setToggling(true)
    await api.put('/api/ai/settings', { enabled: !st.enabled }).catch(() => {})
    setToggling(false); load()
  }

  if (!st) return <div className="empty">در حال بارگذاری…</div>
  const budgetPct = st.budget ? Math.min(100, (st.cost_month / st.budget) * 100) : 0
  const steps = [
    [st.has_key, `کلید سرویس «${st.provider_label}» روی سرور تنظیم شده (${st.key_env})`, '#/ai/settings'],
    [counts.info, 'اطلاعات کسب‌وکار نوشته شده (آدرس، ساعت کاری، اقساط، گارانتی…)', '#/ai/settings'],
    [counts.products > 0, `فهرست محصول و قیمت وارد شده (${fa(counts.products)} مورد)`, '#/ai/products'],
    [counts.faq > 0, `پرسش‌های رایج ثبت شده (${fa(counts.faq)} مورد)`, '#/ai/faq'],
    [counts.docs > 0, `فایل کاتالوگ یا پاسخنامه بارگذاری شده (${fa(counts.docs)} فایل)`, '#/ai/docs'],
  ]
  const intents = Object.entries(st.intents_7d || {})
  const maxIntent = Math.max(1, ...intents.map(([, n]) => n))

  return (
    <>
      <section className="card">
        <div className="row-between">
          <div>
            <h2 style={{ margin: 0 }}>ربات هوشمند</h2>
            <p className="muted" style={{ margin: 0 }}>وقتی هیچ دستوری به پیام نخورد، ربات با پایگاه دانش جواب می‌دهد. سرویس: {st.provider_label} · مدل: {st.model}{st.fallback ? ` · پشتیبان: ${st.fallback}` : ''}</p>
          </div>
          <label className="switch"><input type="checkbox" checked={st.enabled} disabled={toggling} onChange={toggle} /><span /> {st.enabled ? 'روشن' : 'خاموش'}</label>
        </div>
        <p className="muted" style={{ margin: '6px 0 0' }}>موتور فهم (اینستاگرام): {st.brain_enabled ? 'روشن ✅' : 'خاموش'}{st.brain_ready ? '' : ' · دانش ربات تلگرام هنوز روی سرور پیدا نشد'} <a href="#/ai/settings">تغییر</a></p>
        {st.enabled && !st.has_key && <p className="err">کلید API ثبت نشده؛ در «تنظیمات مغز ← کلید سرویس‌های هوش مصنوعی» بگذارید (یا سرویس دیگری انتخاب کنید).</p>}
      </section>

      <section className="card">
        <h2>۲۴ ساعت گذشته</h2>
        <div className="tiles">
          <div className="tile good"><b>{fa(st.replies_24h)}</b><span>پاسخ هوشمند</span></div>
          <a href="#/ai/handoffs" className={`tile ${st.handoffs_open ? 'warn' : ''}`}><b>{fa(st.handoffs_open)}</b><span>ارجاع باز به شما</span></a>
          <div className="tile"><b>{fa(st.ignored_24h)}</b><span>نادیده (اسپم، ایموجی)</span></div>
          <a href="#/ai/log" className={`tile ${st.errors_24h ? 'bad' : ''}`}><b>{fa(st.errors_24h)}</b><span>خطا</span></a>
        </div>
        <div style={{ marginTop: 12 }}>
          <div className="row-between muted"><span>هزینه‌ی این ماه</span><span>{usd(st.cost_month)} از {usd(st.budget)}</span></div>
          <div className="progress"><div style={{ width: `${budgetPct}%` }} className={budgetPct > 85 ? 'bad' : ''} /></div>
        </div>
      </section>

      <section className="card">
        <h2>راه‌اندازی</h2>
        <div className="list">
          {steps.map(([done, label, href]) => (
            <div key={label} className="check-row">
              <span className={`dot ${done ? 'on' : ''}`}>{done ? '✓' : ''}</span>
              {href && !done ? <a href={href}>{label}</a> : <span className={done ? '' : 'muted'}>{label}</span>}
            </div>
          ))}
        </div>
      </section>

      <Sandbox />

      {intents.length > 0 && (
        <section className="card">
          <h2>موضوع پیام‌ها در ۷ روز گذشته</h2>
          <IntentBars intents={intents} max={maxIntent} />
        </section>
      )}
    </>
  )
}

const INTENT_FA = { greeting: 'سلام', price: 'قیمت', availability: 'موجودی', installment: 'اقساط', purchase: 'قصد خرید',
  support: 'پشتیبانی', complaint: 'شکایت', thanks: 'تشکر', spam: 'اسپم', other: 'سایر' }

function IntentBars({ intents, max }) {
  return (
    <div className="bars">
      {intents.map(([k, n]) => (
        <div key={k} className="bar-row">
          <span>{INTENT_FA[k] || k}</span>
          <div className="bar"><div style={{ width: `${(n / max) * 100}%` }} /></div>
          <b>{fa(n)}</b>
        </div>
      ))}
    </div>
  )
}

function Sandbox() {
  const [ch, setCh] = useState('dm')
  const [text, setText] = useState('')
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  async function run(e) {
    e.preventDefault(); setBusy(true); setRes(null)
    try { setRes(await api.post('/api/ai/test', { channel: ch, text })) }
    catch (ex) { setRes({ error: ex.message }) }
    finally { setBusy(false) }
  }
  return (
    <form className="card" onSubmit={run}>
      <h2>آزمایش ربات</h2>
      <p className="muted">یک پیام فرضی بنویسید و جواب ربات را ببینید. چیزی برای کسی فرستاده نمی‌شود، ولی هزینه‌ی API دارد.</p>
      <div className="actions" style={{ marginBottom: 8 }}>
        <button type="button" className={`chip ${ch === 'dm' ? 'active' : ''}`} onClick={() => setCh('dm')}>دایرکت</button>
        <button type="button" className={`chip ${ch === 'comment' ? 'active' : ''}`} onClick={() => setCh('comment')}>کامنت</button>
      </div>
      <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="مثلاً: ۱۳ پرومکس کارکرده دارید؟ قسطی هم میدید؟" />
      <div className="actions" style={{ marginTop: 8 }}><button className="btn primary" disabled={busy || !text.trim()}>{busy ? 'در حال فکر کردن…' : 'بفرست'}</button></div>
      {res && (res.error && !res.action ? <p className="err">{res.error}</p> : (
        <div className="result">
          <div className="row-between">
            <span className={`pill ${ACTION_CLS[res.action]}`}>{ACTION_FA[res.action]}</span>
            <span className="muted">{INTENT_FA[res.intent] || ''} {res.confidence ? `· اطمینان ${fa(Math.round(res.confidence * 100))}٪` : ''} · {usd(res.cost)}</span>
          </div>
          {res.reply && <div className="bubble out" style={{ maxWidth: '100%' }}><span className="label">{ch === 'comment' ? 'دایرکت به کامنت‌گذار' : 'پاسخ'}</span>{res.reply}</div>}
          {res.public_reply && <div className="bubble in" style={{ maxWidth: '100%' }}><span className="label">پاسخ عمومی زیر کامنت</span>{res.public_reply}</div>}
          {res.handoff_reason && <p className="muted">دلیل ارجاع: {res.handoff_reason}</p>}
          {res.skip_reason && <p className="muted">رد شد: {SKIP_FA[res.skip_reason] || res.skip_reason}</p>}
          {res.error && <p className="err">{res.error}</p>}
        </div>
      ))}
    </form>
  )
}

// ---------- ارجاع به شما ----------

function Handoffs() {
  const [status, setStatus] = useState('open')
  const [items, setItems] = useState([])
  const load = () => api.get(`/api/ai/handoffs?status=${status}`).then(setItems).catch(() => {})
  useEffect(() => { load() }, [status])
  async function resolve(h, done) { await api.post(`/api/ai/handoffs/${h.id}/resolve`, { done }); load() }
  return (
    <>
      <div className="chips">
        {[['open', 'باز'], ['done', 'انجام‌شده'], ['all', 'همه']].map(([k, l]) => (
          <button key={k} className={`chip ${status === k ? 'active' : ''}`} onClick={() => setStatus(k)}>{l}</button>
        ))}
      </div>
      <p className="muted">پیام‌هایی که ربات جواب کاملش را نداشت یا مشتری قصد خرید یا شکایت داشت. ربات به مشتری گفته که همکار انسانی جواب می‌دهد.</p>
      {!items.length && <div className="empty">{status === 'open' ? 'ارجاع بازی نیست 🎉' : 'موردی نیست'}</div>}
      <div className="list">
        {items.map((h) => (
          <div key={h.id} className="item" style={{ cursor: 'default' }}>
            <div className="row">
              <span className="who">{h.username || h.user_id} <span className="pill muted">{h.channel === 'comment' ? 'کامنت' : 'دایرکت'}</span> {h.intent && <span className="pill warn">{INTENT_FA[h.intent] || h.intent}</span>}</span>
              <span className="when">{timeAgo(h.created_at)}</span>
            </div>
            <div className="text">{h.text}</div>
            {h.reason && <p className="muted" style={{ margin: '4px 0' }}>دلیل: {h.reason}</p>}
            {h.bot_reply && <div className="bubble out" style={{ maxWidth: '100%', marginTop: 6 }}><span className="label">ربات گفت</span>{h.bot_reply}</div>}
            <div className="actions" style={{ marginTop: 8 }}>
              <a className="btn sm primary" href={h.channel === 'dm' ? `#/messages/${h.user_id}` : '#/comments'}>جواب بده</a>
              {h.status === 'open'
                ? <button className="btn sm" onClick={() => resolve(h, true)}>انجام شد ✓</button>
                : <button className="btn sm" onClick={() => resolve(h, false)}>باز کردن دوباره</button>}
            </div>
          </div>
        ))}
      </div>
    </>
  )
}

// ---------- تنظیمات ربات ----------

const INFO_TEMPLATE = `آدرس فروشگاه: …
ساعت کاری: شنبه تا پنج‌شنبه ۱۰ تا ۲۲
شماره تماس / واتساپ: …
ارسال: به همه‌ی شهرها با پست پیشتاز، هزینه‌ی ارسال …
گارانتی: …
شرایط اقساط: پیش‌پرداخت …٪، تعداد اقساط …، مدارک لازم …
خرید گوشی کارکرده‌ی مشتری (تعویض): …
روش پرداخت: …`

function Settings() {
  const [s, setS] = useState(null)
  const [providers, setProviders] = useState([])
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { api.get('/api/ai/settings').then((r) => { setS(r.settings); setProviders(r.providers) }) }, [])
  useEffect(() => {   // کلید تازه از بخش «کلید سرویس‌ها» → وضعیت سرویس‌ها به‌روز شود
    const on = () => api.get('/api/ai/settings').then((r) => setProviders(r.providers)).catch(() => {})
    window.addEventListener('ai:keys', on)
    return () => window.removeEventListener('ai:keys', on)
  }, [])
  if (!s) return <div className="empty">در حال بارگذاری…</div>
  const set = (patch) => setS({ ...s, ...patch })
  const prov = providers.find((p) => p.id === s.provider)
  const fb = providers.find((p) => p.id === s.fallback_provider)

  async function save(e) {
    e.preventDefault(); setBusy(true); setMsg(null)
    try {
      const r = await api.put('/api/ai/settings', Object.fromEntries(Object.entries(s).filter(([k]) => !IG_KEYS.includes(k))))
      setS(r.settings); setMsg({ ok: true, text: 'ذخیره شد ✅' })
    } catch (ex) { setMsg({ ok: false, text: ex.message }) }
    finally { setBusy(false) }
  }

  const MODEL_FA = {
    'claude-opus-5-5': 'Opus 5.5 — بهترین کیفیت (هر پاسخ حدود ۰٫۵ تا ۱ سنت)',
    'claude-sonnet-5-5': 'Sonnet 5.5 — کیفیت خوب، نصف هزینه',
    'claude-haiku-5-5': 'Haiku 5.5 — سریع و خیلی ارزان (حدود ۴۰ برابر ارزان‌تر از Opus)',
  }

  return (
    <form onSubmit={save}>
      <section className="card">
        <h2>روشن و خاموش</h2>
        <label className="check"><input type="checkbox" checked={s.brain_enabled} onChange={(e) => set({ brain_enabled: e.target.checked })} /> موتور فهم روشن باشد (رایگان، بدون کلید)</label>
        <p className="hint muted">دانش مرکزی، فهرست کالای سایت، آدرس، اقساط، ساعت کاری و مقایسه‌ی آیفون‌ها. در تلگرام همیشه فعال است؛ این کلید برای اینستاگرام است. اول این جواب می‌دهد؛ اگر نفهمید، نوبت هوش مصنوعی است (اگر روشن باشد)، وگرنه به شما ارجاع می‌شود.</p>
        <label className="check"><input type="checkbox" checked={s.enabled} onChange={(e) => set({ enabled: e.target.checked })} /> هوش مصنوعی روشن باشد، برای همه‌ی کانال‌ها (برای سؤال‌هایی که موتور فهم جواب نداد؛ کلید API لازم است)</label>
        <p className="hint muted">روشن و خاموش هر کانال و تنظیم‌های مخصوص آن (مثل نحوه‌ی جواب به کامنت) در «کانال‌ها» است.</p>
        <label className="check"><input type="checkbox" checked={s.skip_emoji_only} onChange={(e) => set({ skip_emoji_only: e.target.checked })} /> پیام‌هایی که فقط ایموجی‌اند را نادیده بگیرد (بدون هزینه)</label>
      </section>

      <section className="card">
        <h2>اطلاعات کسب‌وکار</h2>
        <p className="muted">هر چیزی که ربات باید بداند و در فهرست محصول یا پرسش‌های رایج نیست. ربات چیزی را که اینجا نباشد از خودش نمی‌سازد.</p>
        <textarea rows={9} value={s.business_info} placeholder={INFO_TEMPLATE} onChange={(e) => set({ business_info: e.target.value })} />
        {!s.business_info && <button type="button" className="btn sm" style={{ marginTop: 6 }} onClick={() => set({ business_info: INFO_TEMPLATE })}>درج الگو</button>}
      </section>

      <section className="card">
        <h2>لحن و سبک</h2>
        <div className="field">
          <label>لحن</label>
          <div className="actions">
            {[['formal', 'رسمی'], ['friendly', 'دوستانه'], ['casual', 'خودمانی']].map(([k, l]) => (
              <button type="button" key={k} className={`chip ${s.tone === k ? 'active' : ''}`} onClick={() => set({ tone: k })}>{l}</button>
            ))}
          </div>
        </div>
        <div className="field">
          <label>طول پاسخ</label>
          <div className="actions">
            {[['short', 'کوتاه'], ['medium', 'متوسط']].map(([k, l]) => (
              <button type="button" key={k} className={`chip ${s.length === k ? 'active' : ''}`} onClick={() => set({ length: k })}>{l}</button>
            ))}
          </div>
        </div>
      </section>

      <section className="card">
        <h2>فروشندگی</h2>
        <p className="muted">ربات مثل یک فروشنده‌ی زبل رفتار کند: جواب دقیق، پیشنهاد جایگزین وقتی محصول نیست، سؤال برای فهم نیاز مشتری، و دعوت به خرید. همه‌چیز فقط از روی فهرست محصول و اطلاعات شما.</p>
        <label className="check"><input type="checkbox" checked={s.sales_mode} onChange={(e) => set({ sales_mode: e.target.checked })} /> حالت فروشنده روشن باشد</label>
        {s.sales_mode && (
          <>
            <label className="check"><input type="checkbox" checked={s.send_links} onChange={(e) => set({ send_links: e.target.checked })} /> لینک محصول سایت را در دایرکت بفرستد</label>
            <label className="check"><input type="checkbox" checked={s.upsell} onChange={(e) => set({ upsell: e.target.checked })} /> به خریدار گوشی، یک لوازم جانبی موجود (کابل، شارژر…) پیشنهاد بدهد</label>
            <label className="check"><input type="checkbox" checked={s.ask_contact} onChange={(e) => set({ ask_contact: e.target.checked })} /> برای سفارش قطعی، شماره‌ی تماس مشتری را بخواهد</label>
            <div className="field">
              <label>راه خرید (در دعوت به خرید گفته می‌شود)</label>
              <input type="text" value={s.cta} placeholder="مثلاً: خرید آنلاین از stland.ir یا حضوری در فروشگاه، هماهنگی در دایرکت" onChange={(e) => set({ cta: e.target.value })} />
            </div>
          </>
        )}
      </section>


      <section className="card">
        <h2>ارجاع به شما</h2>
        <div className="field">
          <label>حداقل اطمینان برای جواب مستقیم: {fa(Math.round(s.min_confidence * 100))}٪</label>
          <input type="range" min="0" max="1" step="0.05" value={s.min_confidence} onChange={(e) => set({ min_confidence: Number(e.target.value) })} />
          <p className="hint muted">اگر ربات کمتر از این مطمئن باشد، به‌جای جواب دادن به شما ارجاع می‌دهد. بالاتر یعنی محتاط‌تر.</p>
        </div>
        <div className="field">
          <label>پیام به مشتری هنگام ارجاع</label>
          <input type="text" value={s.handoff_message} onChange={(e) => set({ handoff_message: e.target.value })} />
        </div>
      </section>

      <section className="card">
        <h2>مدل و هزینه</h2>
        <div className="field">
          <label>سرویس هوش مصنوعی</label>
          <select value={s.provider} onChange={(e) => {
            const p = providers.find((x) => x.id === e.target.value)
            set({ provider: p.id, model: p.models[0] || '', fallback_provider: s.fallback_provider === p.id ? '' : s.fallback_provider })
          }}>
            {providers.map((p) => <option key={p.id} value={p.id}>{p.label} {p.configured ? '✅' : '— کلید ندارد'}</option>)}
          </select>
          {prov && !prov.configured && <p className="hint err">کلید این سرویس ثبت نشده؛ در بخش «کلید سرویس‌های هوش مصنوعی» بالای همین صفحه بگذارید.</p>}
        </div>
        <div className="field">
          <label>مدل</label>
          {prov?.claude ? (
            <select value={s.model} onChange={(e) => set({ model: e.target.value })}>
              {prov.models.map((m) => <option key={m} value={m}>{MODEL_FA[m] || m}</option>)}
            </select>
          ) : (
            <>
              <input type="text" dir="ltr" list="ai-models" value={s.model} placeholder="نام مدل، مثلاً gpt-4.1-mini" onChange={(e) => set({ model: e.target.value })} />
              <datalist id="ai-models">{(prov?.models || []).map((m) => <option key={m} value={m} />)}</datalist>
              <p className="hint muted">نام دقیق مدل را از سایت همان سرویس بردارید؛ فهرست بالا فقط پیشنهاد است.</p>
            </>
          )}
        </div>
        {prov && !prov.claude && (
          <div className="field">
            <label>قیمت مدل (دلار برای هر یک میلیون توکن) — برای محاسبه‌ی هزینه و سقف ماهانه</label>
            <div className="actions">
              <input type="number" min="0" step="0.01" value={s.price_in} onChange={(e) => set({ price_in: Number(e.target.value) })} placeholder="ورودی" />
              <input type="number" min="0" step="0.01" value={s.price_out} onChange={(e) => set({ price_out: Number(e.target.value) })} placeholder="خروجی" />
            </div>
            <p className="hint muted">ورودی و خروجی را از صفحه‌ی قیمت سرویس وارد کنید. صفر یعنی نامعلوم؛ آن وقت هزینه صفر ثبت می‌شود و سقف ماهانه کار نمی‌کند.</p>
          </div>
        )}
        <div className="field">
          <label>سرویس پشتیبان (اگر سرویس اصلی خطا داد یا در دسترس نبود)</label>
          <select value={s.fallback_provider} onChange={(e) => {
            const p = providers.find((x) => x.id === e.target.value)
            set({ fallback_provider: e.target.value, fallback_model: p ? (p.models[0] || '') : '' })
          }}>
            <option value="">بدون پشتیبان</option>
            {providers.filter((p) => p.id !== s.provider).map((p) => <option key={p.id} value={p.id}>{p.label} {p.configured ? '✅' : '— کلید ندارد'}</option>)}
          </select>
          {fb && (
            <>
              <input type="text" dir="ltr" list="ai-fb-models" style={{ marginTop: 6 }} value={s.fallback_model} placeholder="مدل پشتیبان" onChange={(e) => set({ fallback_model: e.target.value })} />
              <datalist id="ai-fb-models">{fb.models.map((m) => <option key={m} value={m} />)}</datalist>
              {!fb.claude && <p className="hint muted">هزینه‌ی سرویس پشتیبان هم با همان قیمت بالا حساب می‌شود.</p>}
            </>
          )}
        </div>
        <div className="field">
          <label>دقت فکر کردن {prov && !prov.claude && '(فقط برای Claude)'}</label>
          <div className="actions">
            {[['low', 'سریع'], ['medium', 'متعادل'], ['high', 'دقیق']].map(([k, l]) => (
              <button type="button" key={k} className={`chip ${s.effort === k ? 'active' : ''}`} onClick={() => set({ effort: k })}>{l}</button>
            ))}
          </div>
          <p className="hint muted">برای جواب مشتری «سریع» کافی است. دقیق‌تر یعنی کندتر و گران‌تر.</p>
        </div>
        <div className="field">
          <label>تعداد پیام‌های قبلی گفتگو که ربات می‌بیند</label>
          <input type="number" min="0" max="30" value={s.history_messages} onChange={(e) => set({ history_messages: Number(e.target.value) })} />
        </div>
        <div className="field">
          <label>سقف هزینه‌ی ماهانه (دلار)</label>
          <input type="number" min="0" step="1" value={s.monthly_budget_usd} onChange={(e) => set({ monthly_budget_usd: Number(e.target.value) })} />
          <p className="hint muted">وقتی هزینه‌ی ماه به این عدد برسد، ربات تا اول ماه بعد جواب نمی‌دهد. صفر یعنی بدون سقف.</p>
        </div>
      </section>

      <Msg m={msg} />
      <div className="actions sticky-save"><button className="btn primary" disabled={busy}>ذخیره‌ی تنظیمات</button></div>
    </form>
  )
}

// ---------- پرسش‌های رایج ----------

const EMPTY_FAQ = { question: '', keywords: '', answer: '', enabled: true }

const EMPTY_INTENT = { id: '', keys: '', examples: '', answer: '', action: '', enabled: true }
const firstVariant = (a) => (a || '').split('\n---\n')[0]

function Kb() {
  const [kb, setKb] = useState(null)
  const [edit, setEdit] = useState(null)
  const [q, setQ] = useState('')
  const [msg, setMsg] = useState(null)
  const [sec, setSec] = useState({})
  const load = () => api.get('/api/ai/kb').then((r) => {
    setKb(r); setSec(Object.fromEntries(r.sections.map((v) => [v.key, v.text])))
  }).catch(() => {})
  useEffect(() => { load() }, [])
  const later = () => setTimeout(load, 3500)
  const shown = useMemo(() => (kb?.intents || []).filter((x) => !q || `${x.keys.join(' ')} ${x.examples.join(' ')} ${x.answer}`.includes(q)), [kb, q])

  if (!kb) return <div className="empty">در حال بارگذاری…</div>
  if (!kb.ready) return (
    <>
      <p className="err">دانش مرکزی هنوز در دسترس نیست: ربات تلگرام روی این سرور منتقل نشده. تا آن موقع پرسش‌های رایج فقط برای اینستاگرام است.</p>
      <Faq />
    </>
  )
  const ok = (text) => { setMsg({ ok: true, text }); later() }
  const fail = (ex) => setMsg({ ok: false, text: ex.message })

  async function save(e) {
    e.preventDefault(); setMsg(null)
    try { await api.post('/api/ai/kb/intents', edit); setEdit(null); ok('ثبت شد ✅ تا چند ثانیه در همه‌ی کانال‌ها فعال می‌شود.') } catch (ex) { fail(ex) }
  }
  async function toggle(x) {
    try { await api.post('/api/ai/kb/intents', { ...x, enabled: !x.enabled }); ok(x.enabled ? 'خاموش شد' : 'روشن شد') } catch (ex) { fail(ex) }
  }
  async function remove(x) {
    const warn = x.builtin ? ' (این از پیش‌فرض‌های ربات است؛ بهتر است به‌جای حذف خاموشش کنید)' : ''
    if (!confirm(`حذف شود؟${warn}`)) return
    try { await api.del(`/api/ai/kb/intents/${x.id}`); ok('حذف شد') } catch (ex) { fail(ex) }
  }
  async function saveSection(k) {
    try { await api.put(`/api/ai/kb/sections/${k}`, { text: sec[k] || '' }); ok('متن بخش ثبت شد ✅') } catch (ex) { fail(ex) }
  }
  async function migrate() {
    try { const r = await api.post('/api/ai/kb/migrate-faq'); ok(`${fa(r.moved)} پرسش به دانش مرکزی منتقل شد ✅`) } catch (ex) { fail(ex) }
  }

  return (
    <>
      <p className="muted">دانش کل پروژه: یک بار اینجا وارد کنید؛ همه‌ی کانال‌ها (الان تلگرام و اینستاگرام) همین را جواب می‌دهند و هوش مصنوعی هم همین را می‌شناسد. از پنل داخل تلگرام هم قابل ویرایش است.</p>
      {kb.pending.count > 0 && (
        <p className={kb.pending.stale ? 'err' : 'muted'}>
          {kb.pending.stale ? `⚠️ ${fa(kb.pending.count)} تغییر منتظر است و ربات تلگرام برشان نداشته؛ سرویس igbot-telegram روشن است؟` : `⏳ ${fa(kb.pending.count)} تغییر در حال اعمال…`}
        </p>
      )}
      {kb.old_faq > 0 && (
        <div className="card">
          <p style={{ margin: 0 }}>{fa(kb.old_faq)} پرسش رایج قدیمی فقط برای اینستاگرام ثبت شده.</p>
          <button className="btn primary sm" style={{ marginTop: 8 }} onClick={migrate}>انتقال به دانش مرکزی</button>
        </div>
      )}
      <Msg m={msg} />

      {edit && (
        <form className="card" onSubmit={save}>
          <h2>{edit.id ? 'ویرایش' : 'پرسش یا دستور تازه'}</h2>
          <div className="field">
            <label>کلیدواژه‌ها (با ویرگول جدا)</label>
            <input type="text" value={edit.keys} onChange={(e) => setEdit({ ...edit, keys: e.target.value })} placeholder="مثلاً: تعمیر، تعمیرات، خرابی" autoFocus />
          </div>
          <div className="field">
            <label>جمله‌های نمونه‌ی مشتری (هر خط یکی)</label>
            <textarea rows={3} value={edit.examples} onChange={(e) => setEdit({ ...edit, examples: e.target.value })} placeholder={'گوشیمو تعمیر میکنید؟\nصفحه‌ی آیفون عوض میکنید؟'} />
            <p className="hint muted">ربات با غلط تایپی و شکل‌های دیگر جمله هم می‌فهمد؛ چند نمونه‌ی متفاوت کافی است.</p>
          </div>
          <div className="field">
            <label>جواب</label>
            <textarea rows={5} value={edit.answer} onChange={(e) => setEdit({ ...edit, answer: e.target.value })} />
            <p className="hint muted">برای چند شکل جواب (ربات هر بار یکی را می‌گوید)، بین آن‌ها یک خط فقط با --- بگذارید. {'{product}'} جای نام مدلی می‌نشیند که مشتری گفته.</p>
          </div>
          <div className="field">
            <label>کار همراه جواب</label>
            <select value={edit.action} onChange={(e) => setEdit({ ...edit, action: e.target.value })}>
              {Object.entries(kb.actions).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </div>
          <label className="check"><input type="checkbox" checked={edit.enabled} onChange={(e) => setEdit({ ...edit, enabled: e.target.checked })} /> فعال</label>
          <div className="actions"><button className="btn primary">ذخیره</button><button type="button" className="btn" onClick={() => setEdit(null)}>انصراف</button></div>
        </form>
      )}

      {!edit && (
        <>
          <details className="card">
            <summary><b>متن‌های پایه</b> <span className="muted">— آدرس، اقساط، تماس، سایت…</span></summary>
            <p className="muted">در همه‌ی کانال‌ها همین متن می‌آید (منوی تلگرام، جواب اینستاگرام، هوش مصنوعی).</p>
            {kb.sections.map((v) => (
              <div className="field" key={v.key}>
                <label>{v.title}</label>
                <textarea rows={3} value={sec[v.key] || ''} onChange={(e) => setSec({ ...sec, [v.key]: e.target.value })} />
                {(sec[v.key] || '') !== v.text && <button type="button" className="btn sm primary" style={{ marginTop: 4 }} onClick={() => saveSection(v.key)}>ذخیره‌ی {v.title}</button>}
              </div>
            ))}
          </details>

          <div className="actions" style={{ marginBottom: 10 }}>
            <button className="btn primary" onClick={() => setEdit(EMPTY_INTENT)}>+ پرسش یا دستور تازه</button>
            <input type="text" style={{ flex: 1, minWidth: 140 }} placeholder="جست‌وجو…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <p className="muted">{fa(kb.intents.length)} پرسش و دستور · {fa(kb.intents.filter((x) => x.enabled).length)} فعال</p>
          <div className="list">
            {shown.map((x) => (
              <div key={x.id} className={`item ${x.enabled ? '' : 'disabled'}`} style={{ cursor: 'default' }}>
                <div className="row">
                  <span className="who">{(x.keys.length ? x.keys : x.examples).slice(0, 4).join('، ')}</span>
                  <span className="muted">{fa(x.hits)} بار</span>
                </div>
                <p className="text" style={{ whiteSpace: 'pre-line' }}>{firstVariant(x.answer).slice(0, 220) || '—'}</p>
                <div className="row">
                  <span>{x.action && <span className="pill muted">{kb.actions[x.action] || x.action}</span>}</span>
                  <span className="actions">
                    <button className={`btn sm ${x.enabled ? '' : 'primary'}`} onClick={() => toggle(x)}>{x.enabled ? 'خاموش' : 'روشن'}</button>
                    <button className="btn sm" onClick={() => setEdit({ ...x, keys: x.keys.join('، '), examples: x.examples.join('\n') })}>ویرایش</button>
                    <button className="btn sm danger" onClick={() => remove(x)}>حذف</button>
                  </span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  )
}

function Faq() {
  const [items, setItems] = useState([])
  const [edit, setEdit] = useState(null)
  const [q, setQ] = useState('')
  const [msg, setMsg] = useState(null)
  const load = () => api.get('/api/ai/faq').then(setItems).catch(() => {})
  useEffect(() => { load() }, [])
  const shown = useMemo(() => items.filter((f) => !q || `${f.question} ${f.keywords} ${f.answer}`.includes(q)), [items, q])

  async function save(e) {
    e.preventDefault(); setMsg(null)
    try {
      if (edit.id) await api.put(`/api/ai/faq/${edit.id}`, edit); else await api.post('/api/ai/faq', edit)
      setEdit(null); load()
    } catch (ex) { setMsg({ ok: false, text: ex.message }) }
  }
  async function remove(f) { if (confirm('این پرسش حذف شود؟')) { await api.del(`/api/ai/faq/${f.id}`); load() } }

  return (
    <>
      <p className="muted">پاسخ‌های دقیقی که ربات باید بدهد. ربات مفهوم را می‌فهمد؛ لازم نیست مشتری دقیقاً همین جمله را بنویسد. کلمات کلیدی فقط برای آمار و جست‌وجوست.</p>
      {edit ? (
        <form className="card" onSubmit={save}>
          <h2>{edit.id ? 'ویرایش پرسش' : 'پرسش جدید'}</h2>
          <div className="field"><label>پرسش</label><input type="text" value={edit.question} onChange={(e) => setEdit({ ...edit, question: e.target.value })} placeholder="مثلاً: اقساطی هم می‌فروشید؟" autoFocus /></div>
          <div className="field"><label>کلمات کلیدی (با کاما)</label><input type="text" value={edit.keywords} onChange={(e) => setEdit({ ...edit, keywords: e.target.value })} placeholder="قسط، اقساط، قسطی" /></div>
          <div className="field"><label>پاسخ</label><textarea rows={4} value={edit.answer} onChange={(e) => setEdit({ ...edit, answer: e.target.value })} /></div>
          <label className="check"><input type="checkbox" checked={edit.enabled} onChange={(e) => setEdit({ ...edit, enabled: e.target.checked })} /> فعال</label>
          <Msg m={msg} />
          <div className="actions"><button className="btn primary">ذخیره</button><button type="button" className="btn" onClick={() => setEdit(null)}>انصراف</button></div>
        </form>
      ) : (
        <div className="actions" style={{ marginBottom: 10 }}>
          <button className="btn primary" onClick={() => setEdit(EMPTY_FAQ)}>+ پرسش جدید</button>
          <input type="text" style={{ flex: 1, minWidth: 140 }} placeholder="جست‌وجو…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      )}
      {!items.length && !edit && <div className="empty">هنوز پرسشی ثبت نشده</div>}
      <div className="list">
        {shown.map((f) => (
          <div key={f.id} className={`item ${f.enabled ? '' : 'disabled'}`} style={{ cursor: 'default' }}>
            <div className="row"><span className="who">{f.question}</span><span className="when">{f.hits ? `${fa(f.hits)} بار` : ''}</span></div>
            <div className="text">{f.answer}</div>
            {f.keywords && <div className="muted">🔑 {f.keywords}</div>}
            <div className="actions" style={{ marginTop: 6 }}>
              <button className="btn sm" onClick={() => setEdit({ ...f, enabled: !!f.enabled })}>ویرایش</button>
              <button className="btn sm danger" onClick={() => remove(f)}>حذف</button>
            </div>
          </div>
        ))}
      </div>
    </>
  )
}

// ---------- محصولات ----------

const COND = { new: 'نو', used: 'کارکرده', stock: 'استوک' }
const EMPTY_P = { name: '', storage: '', color: '', condition: 'new', price: '', in_stock: true, notes: '', enabled: true }

function SiteSync({ onSynced }) {
  const [st, setSt] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  useEffect(() => { api.get('/api/ai/site-sync').then(setSt).catch(() => {}) }, [])
  if (!st) return null
  const set = (patch) => setSt({ ...st, ...patch })

  async function save(e) {
    e.preventDefault(); setBusy(true); setMsg(null)
    try {
      setSt(await api.put('/api/ai/site-sync', { url: st.url, enabled: st.enabled, interval_hours: st.interval_hours, currency: st.currency }))
      setMsg({ ok: true, text: 'ذخیره شد ✅' })
    } catch (ex) { setMsg({ ok: false, text: ex.message }) }
    finally { setBusy(false) }
  }
  async function run() {
    setBusy(true); setMsg(null)
    try {
      await api.put('/api/ai/site-sync', { url: st.url, interval_hours: st.interval_hours, currency: st.currency })
      const r = await api.post('/api/ai/site-sync/run')
      setSt(r)
      setMsg(r.last_error ? { ok: false, text: r.last_error } : { ok: true, text: `${fa(r.last_count)} محصول از سایت خوانده شد ✅` })
      onSynced()
    } catch (ex) { setMsg({ ok: false, text: ex.message }) }
    finally { setBusy(false) }
  }

  return (
    <form className="card" onSubmit={save}>
      <h2>همگام‌سازی با سایت</h2>
      <p className="muted">قیمت و موجودی خودکار از فروشگاه ووکامرس (وردپرس) خوانده می‌شود. محصولات سایت هر بار کامل به‌روز می‌شوند و محصولاتی که دستی وارد کرده‌اید دست نمی‌خورند.</p>
      <div className="field">
        <label>آدرس سایت</label>
        <input type="url" dir="ltr" value={st.url} placeholder="https://example.ir" onChange={(e) => set({ url: e.target.value })} />
      </div>
      <div className="grid2">
        <div className="field">
          <label>هر چند ساعت یک بار</label>
          <input type="number" min="1" max="48" value={st.interval_hours} onChange={(e) => set({ interval_hours: Number(e.target.value) })} />
        </div>
        <div className="field">
          <label>واحد قیمت در سایت</label>
          <select value={st.currency} onChange={(e) => set({ currency: e.target.value })}>
            <option value="auto">خودکار (از تنظیمات ووکامرس)</option>
            <option value="IRT">تومان</option>
            <option value="IRR">ریال</option>
          </select>
        </div>
      </div>
      <label className="check"><input type="checkbox" checked={st.enabled} onChange={(e) => set({ enabled: e.target.checked })} /> همگام‌سازی خودکار روشن باشد</label>
      {st.last_at > 0 && (
        <p className={st.last_error ? 'err' : 'muted'}>
          آخرین همگام‌سازی: {timeAgo(st.last_at)} · {fa(st.last_count)} محصول{st.last_api === 'v3' ? ' (با کلید ووکامرس)' : ''}{st.last_error ? ` · خطا: ${st.last_error}` : ''}
        </p>
      )}
      {st.last_error && !st.has_wc_key && (
        <p className="hint muted">اگر سایت دسترسی عمومی به فهرست محصولات را بسته باشد، در ووکامرس از مسیر تنظیمات ← پیشرفته ← REST API یک کلید «فقط خواندنی» بسازید و WC_CONSUMER_KEY و WC_CONSUMER_SECRET را در ‎.env سرور بگذارید.</p>
      )}
      <Msg m={msg} />
      <div className="actions">
        <button className="btn primary" disabled={busy}>ذخیره</button>
        <button type="button" className="btn" disabled={busy || !st.url} onClick={run}>{busy ? 'در حال خواندن…' : 'همگام‌سازی الان'}</button>
      </div>
    </form>
  )
}

function Products() {
  const [items, setItems] = useState([])
  const [edit, setEdit] = useState(null)
  const [q, setQ] = useState('')
  const [onlyStock, setOnlyStock] = useState(false)
  const [imp, setImp] = useState(null)
  const [msg, setMsg] = useState(null)
  const load = () => api.get('/api/ai/products').then(setItems).catch(() => {})
  useEffect(() => { load() }, [])
  const shown = useMemo(() => items.filter((p) => (!onlyStock || p.in_stock) && (!q || `${p.name} ${p.storage} ${p.color} ${p.notes}`.toLowerCase().includes(q.toLowerCase()))), [items, q, onlyStock])

  async function save(e) {
    e.preventDefault(); setMsg(null)
    try {
      if (edit.id) await api.put(`/api/ai/products/${edit.id}`, edit); else await api.post('/api/ai/products', edit)
      setEdit(null); load()
    } catch (ex) { setMsg({ ok: false, text: ex.message }) }
  }
  async function toggleStock(p) { await api.put(`/api/ai/products/${p.id}`, { ...p, in_stock: !p.in_stock, enabled: !!p.enabled }); load() }
  async function remove(p) { if (confirm(`«${p.name}» حذف شود؟`)) { await api.del(`/api/ai/products/${p.id}`); load() } }
  async function doImport(e) {
    e.preventDefault(); setMsg(null)
    if (imp.replace && !confirm('همه‌ی محصولاتی که دستی وارد شده‌اند پاک و با این فهرست جایگزین شوند؟ (محصولات سایت دست نمی‌خورند)')) return
    try {
      const r = await api.post('/api/ai/products/import', imp)
      setMsg({ ok: true, text: `${fa(r.imported)} محصول وارد شد ✅` }); setImp(null); load()
    } catch (ex) { setMsg({ ok: false, text: ex.message }) }
  }

  return (
    <>
      <p className="muted">ربات قیمت و موجودی را فقط از همین فهرست می‌گوید. قیمت خالی یعنی «استعلام» و ربات مشتری را به شما ارجاع می‌دهد.</p>
      {!edit && !imp && <SiteSync onSynced={load} />}
      <Msg m={msg} />
      {edit && (
        <form className="card" onSubmit={save}>
          <h2>{edit.id ? 'ویرایش محصول' : 'محصول جدید'}</h2>
          {edit.source === 'site' && <p className="hint muted">این محصول از سایت آمده؛ تغییر قیمت یا موجودی اینجا در همگام‌سازی بعدی با مقدار سایت جایگزین می‌شود. برای تغییر ماندگار، در خود سایت عوضش کنید.</p>}
          <div className="grid2">
            <div className="field"><label>نام / مدل</label><input type="text" value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} placeholder="iPhone 13 Pro Max" autoFocus /></div>
            <div className="field"><label>حافظه</label><input type="text" value={edit.storage} onChange={(e) => setEdit({ ...edit, storage: e.target.value })} placeholder="256GB" /></div>
            <div className="field"><label>رنگ</label><input type="text" value={edit.color} onChange={(e) => setEdit({ ...edit, color: e.target.value })} /></div>
            <div className="field"><label>وضعیت</label>
              <select value={edit.condition} onChange={(e) => setEdit({ ...edit, condition: e.target.value })}>
                {Object.entries(COND).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
            </div>
            <div className="field"><label>قیمت (تومان)</label><input type="text" inputMode="numeric" value={edit.price ?? ''} onChange={(e) => setEdit({ ...edit, price: e.target.value })} placeholder="خالی = استعلام" /></div>
            <div className="field"><label>توضیح</label><input type="text" value={edit.notes} onChange={(e) => setEdit({ ...edit, notes: e.target.value })} placeholder="سلامت باتری ۹۰٪، ریجستر شده…" /></div>
          </div>
          <label className="check"><input type="checkbox" checked={edit.in_stock} onChange={(e) => setEdit({ ...edit, in_stock: e.target.checked })} /> موجود است</label>
          <label className="check"><input type="checkbox" checked={edit.enabled} onChange={(e) => setEdit({ ...edit, enabled: e.target.checked })} /> ربات این مورد را ببیند</label>
          <div className="actions"><button className="btn primary">ذخیره</button><button type="button" className="btn" onClick={() => setEdit(null)}>انصراف</button></div>
        </form>
      )}
      {imp && (
        <form className="card" onSubmit={doImport}>
          <h2>وارد کردن از اکسل</h2>
          <p className="muted">ستون‌ها را از اکسل کپی کنید و اینجا بچسبانید، به این ترتیب: نام، حافظه، رنگ، وضعیت (نو/کارکرده/استوک)، قیمت، موجودی (بله/خیر)، توضیح.</p>
          <textarea rows={8} dir="auto" value={imp.text} onChange={(e) => setImp({ ...imp, text: e.target.value })} placeholder={'iPhone 13 Pro Max\t256\tآبی\tکارکرده\t45000000\tبله\tباتری ۸۸٪'} />
          <label className="check"><input type="checkbox" checked={imp.replace} onChange={(e) => setImp({ ...imp, replace: e.target.checked })} /> محصولات دستی فعلی پاک و جایگزین شوند</label>
          <div className="actions"><button className="btn primary" disabled={!imp.text.trim()}>وارد کن</button><button type="button" className="btn" onClick={() => setImp(null)}>انصراف</button></div>
        </form>
      )}
      {!edit && !imp && (
        <div className="actions" style={{ marginBottom: 10 }}>
          <button className="btn primary" onClick={() => setEdit(EMPTY_P)}>+ محصول</button>
          <button className="btn" onClick={() => setImp({ text: '', replace: false })}>وارد کردن از اکسل</button>
          <input type="text" style={{ flex: 1, minWidth: 140 }} placeholder="جست‌وجو…" value={q} onChange={(e) => setQ(e.target.value)} />
          <button type="button" className={`chip ${onlyStock ? 'active' : ''}`} onClick={() => setOnlyStock(!onlyStock)}>فقط موجود</button>
        </div>
      )}
      {!items.length && !edit && !imp && <div className="empty">فهرست محصول خالی است</div>}
      {items.length > 0 && <p className="muted">{fa(items.length)} محصول ({fa(items.filter((p) => p.source === 'site').length)} از سایت) · {fa(items.filter((p) => p.in_stock).length)} موجود</p>}
      <div className="list">
        {shown.map((p) => (
          <div key={p.id} className={`item ${p.enabled ? '' : 'disabled'}`} style={{ cursor: 'default' }}>
            <div className="row">
              <span className="who" dir="auto">{p.name} {p.storage && <span className="muted">{p.storage}</span>} {p.color && <span className="muted">· {p.color}</span>}</span>
              <span className="price">{money(p.price)}</span>
            </div>
            <div className="row" style={{ marginTop: 4 }}>
              <span>{p.source === 'site' && <a className="pill" href={p.url || undefined} target="_blank" rel="noreferrer">سایت</a>} <span className="pill muted">{COND[p.condition]}</span> <button className={`pill ${p.in_stock ? 'good' : 'warn'} as-btn`} onClick={() => toggleStock(p)} title="تغییر موجودی">{p.in_stock ? 'موجود' : 'ناموجود'}</button> {p.notes && <span className="muted">{p.notes}</span>}</span>
              <span className="actions">
                <button className="btn sm" onClick={() => setEdit({ ...p, in_stock: !!p.in_stock, enabled: !!p.enabled, price: p.price ?? '' })}>ویرایش</button>
                <button className="btn sm danger" onClick={() => remove(p)}>حذف</button>
              </span>
            </div>
          </div>
        ))}
      </div>
    </>
  )
}

// ---------- فایل‌ها ----------

function Docs() {
  const [items, setItems] = useState([])
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  const [open, setOpen] = useState({})
  const load = () => api.get('/api/ai/docs').then(setItems).catch(() => {})
  useEffect(() => { load() }, [])

  async function upload(e) {
    const files = [...e.target.files]; e.target.value = ''
    setBusy(true); setMsg(null)
    for (const f of files) {
      try {
        if (f.size > 10 * 1024 * 1024) throw new Error('حجم فایل بیشتر از ۱۰ مگابایت است')
        const r = await api.upload(`/api/ai/docs?name=${encodeURIComponent(f.name)}`, f)
        setMsg({ ok: true, text: `«${f.name}» بارگذاری شد: ${fa(r.chars)} نویسه ✅` })
      } catch (ex) { setMsg({ ok: false, text: `«${f.name}»: ${ex.message}` }) }
    }
    setBusy(false); load()
  }
  async function toggle(d) { await api.post(`/api/ai/docs/${d.id}/enable`, { enabled: !d.enabled }); load() }
  async function remove(d) { if (confirm(`«${d.name}» حذف شود؟`)) { await api.del(`/api/ai/docs/${d.id}`); load() } }
  async function preview(d) {
    if (open[d.id]) return setOpen({ ...open, [d.id]: null })
    const r = await api.get(`/api/ai/docs/${d.id}`); setOpen({ ...open, [d.id]: r.preview })
  }

  return (
    <>
      <label className={`dropzone ${busy ? 'busy' : ''}`}>
        <input type="file" accept=".pdf,.docx,.txt,.md,.csv" multiple onChange={upload} disabled={busy} />
        <span className="big">⬆</span>
        <b>{busy ? 'در حال بارگذاری…' : 'فایل کاتالوگ، شرایط فروش یا پاسخنامه را انتخاب کنید'}</b>
        <span className="muted">PDF، Word یا TXT تا ۱۰ مگابایت. ربات فقط بخش‌های مرتبط با هر سؤال را می‌خواند.</span>
      </label>
      <Msg m={msg} />
      <div className="list">
        {items.map((d) => (
          <div key={d.id} className={`item ${d.enabled ? '' : 'disabled'}`} style={{ cursor: 'default' }}>
            <div className="row"><span className="who" dir="auto">📄 {d.name}</span><span className="when">{timeAgo(d.created_at)}</span></div>
            <div className="muted">{fa(d.chars)} نویسه · {fa(d.chunks)} بخش</div>
            {open[d.id] && <pre className="preview">{open[d.id]}</pre>}
            <div className="actions" style={{ marginTop: 6 }}>
              <button className="btn sm" onClick={() => preview(d)}>{open[d.id] ? 'بستن' : 'پیش‌نمایش متن'}</button>
              <button className="btn sm" onClick={() => toggle(d)}>{d.enabled ? 'غیرفعال کن' : 'فعال کن'}</button>
              <button className="btn sm danger" onClick={() => remove(d)}>حذف</button>
            </div>
          </div>
        ))}
      </div>
    </>
  )
}

// ---------- لاگ ----------

const LOG_FILTERS = [['all', 'همه'], ['reply', 'پاسخ'], ['handoff', 'ارجاع'], ['ignore', 'نادیده'], ['error', 'خطا'], ['bad', 'پاسخ بد'], ['test', 'آزمایشی']]

function Log() {
  const [filter, setFilter] = useState('all')
  const [items, setItems] = useState([])
  const [more, setMore] = useState(false)
  const [fix, setFix] = useState(null)

  const load = async (append = false) => {
    const before = append && items.length ? `&before=${items[items.length - 1].created_at}` : ''
    const r = await api.get(`/api/ai/log?filter=${filter}&limit=50${before}`).catch(() => [])
    setItems(append ? [...items, ...r] : r); setMore(r.length === 50)
  }
  useEffect(() => { load() }, [filter])

  async function feedback(l, fb) {
    await api.post(`/api/ai/log/${l.id}/feedback`, { feedback: fb })
    setItems(items.map((x) => (x.id === l.id ? { ...x, feedback: fb || null } : x)))
    if (fb === 'bad') setFix({ id: l.id, answer: '', keywords: '' })
  }
  async function saveFix(e) {
    e.preventDefault()
    await api.post(`/api/ai/log/${fix.id}/feedback`, { feedback: 'bad', correct_answer: fix.answer, keywords: fix.keywords })
    setFix(null); alertOk()
  }
  const [okMsg, setOkMsg] = useState('')
  const alertOk = () => { setOkMsg('پاسخ درست به پرسش‌های رایج اضافه شد؛ ربات از این به بعد همین را می‌گوید ✅'); setTimeout(() => setOkMsg(''), 5000) }

  return (
    <>
      <div className="chips">{LOG_FILTERS.map(([k, l]) => <button key={k} className={`chip ${filter === k ? 'active' : ''}`} onClick={() => setFilter(k)}>{l}</button>)}</div>
      {okMsg && <p className="ok">{okMsg}</p>}
      {!items.length && <div className="empty">چیزی نیست</div>}
      <div className="list">
        {items.map((l) => (
          <div key={l.id} className="item" style={{ cursor: 'default' }}>
            <div className="row">
              <span className="who">{l.username || l.user_id || '—'} <span className="pill muted">{l.channel === 'comment' ? 'کامنت' : 'دایرکت'}</span> <span className={`pill ${ACTION_CLS[l.action]}`}>{ACTION_FA[l.action]}</span> {l.status === 'failed' && <span className="pill bad">ارسال نشد</span>}</span>
              <span className="when">{timeAgo(l.created_at)}</span>
            </div>
            <div className="text">«{l.input}»</div>
            {l.reply && <div className="bubble out" style={{ maxWidth: '100%', marginTop: 6 }}>{l.reply}</div>}
            {l.public_reply && <div className="bubble in" style={{ maxWidth: '100%', marginTop: 6 }}><span className="label">عمومی</span>{l.public_reply}</div>}
            <div className="muted" style={{ marginTop: 4 }}>
              {[l.intent && (INTENT_FA[l.intent] || l.intent), l.confidence ? `اطمینان ${fa(Math.round(l.confidence * 100))}٪` : '',
                l.handoff_reason && `دلیل ارجاع: ${l.handoff_reason}`, l.skip_reason && (SKIP_FA[l.skip_reason] || l.skip_reason),
                l.cost ? usd(l.cost) : ''].filter(Boolean).join(' · ')}
            </div>
            {l.error && <div className="err">{l.error}</div>}
            {(l.reply || l.public_reply) && (
              <div className="actions" style={{ marginTop: 6 }}>
                <button className={`btn sm ${l.feedback === 'good' ? 'primary' : ''}`} onClick={() => feedback(l, l.feedback === 'good' ? '' : 'good')}>👍 خوب</button>
                <button className={`btn sm ${l.feedback === 'bad' ? 'danger' : ''}`} onClick={() => feedback(l, l.feedback === 'bad' ? '' : 'bad')}>👎 بد</button>
              </div>
            )}
            {fix && fix.id === l.id && (
              <form className="replybox" onSubmit={saveFix}>
                <textarea value={fix.answer} onChange={(e) => setFix({ ...fix, answer: e.target.value })} placeholder="پاسخ درست چه بود؟ به پرسش‌های رایج اضافه می‌شود." autoFocus />
                <input type="text" value={fix.keywords} onChange={(e) => setFix({ ...fix, keywords: e.target.value })} placeholder="کلمات کلیدی (اختیاری)" />
                <div className="actions"><button className="btn primary" disabled={!fix.answer.trim()}>افزودن به پایگاه دانش</button><button type="button" className="btn" onClick={() => setFix(null)}>بعداً</button></div>
              </form>
            )}
          </div>
        ))}
      </div>
      {more && <div className="actions" style={{ justifyContent: 'center', marginTop: 10 }}><button className="btn" onClick={() => load(true)}>بیشتر</button></div>}
    </>
  )
}

// ---------- مسدودها ----------

export function Blocked() {
  const [items, setItems] = useState([])
  const [form, setForm] = useState({ user_id: '', username: '', reason: '' })
  const load = () => api.get('/api/ai/blocked').then(setItems).catch(() => {})
  useEffect(() => { load() }, [])
  async function add(e) { e.preventDefault(); await api.post('/api/ai/blocked', form); setForm({ user_id: '', username: '', reason: '' }); load() }
  async function remove(b) { await api.del(`/api/ai/blocked/${b.user_id}`); load() }
  return (
    <>
      <p className="muted">ربات (دستورها و هوش مصنوعی) به این کاربران هیچ جوابی نمی‌دهد. راحت‌ترین راه مسدود کردن، دکمه‌ی «مسدود» در صفحه‌ی کامنت یا گفتگوست.</p>
      <form className="card" onSubmit={add}>
        <div className="grid2">
          <div className="field"><label>شناسه‌ی عددی کاربر</label><input type="text" dir="ltr" value={form.user_id} onChange={(e) => setForm({ ...form, user_id: e.target.value })} /></div>
          <div className="field"><label>نام کاربری (اختیاری)</label><input type="text" dir="ltr" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></div>
        </div>
        <div className="field"><label>دلیل</label><input type="text" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} placeholder="اسپم، رقیب…" /></div>
        <button className="btn primary" disabled={!form.user_id.trim()}>مسدود کن</button>
      </form>
      {!items.length && <div className="empty">کسی مسدود نیست</div>}
      <div className="list">
        {items.map((b) => (
          <div key={b.user_id} className="item" style={{ cursor: 'default' }}>
            <div className="row"><span className="who" dir="ltr">{b.username ? `@${b.username}` : b.user_id}</span><span className="when">{timeAgo(b.created_at)}</span></div>
            {b.reason && <div className="muted">{b.reason}</div>}
            <div className="actions" style={{ marginTop: 6 }}><button className="btn sm" onClick={() => remove(b)}>رفع مسدودی</button></div>
          </div>
        ))}
      </div>
    </>
  )
}
