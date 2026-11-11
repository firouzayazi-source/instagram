import React, { useEffect, useState } from 'react'
import { api, fa, timeAgo } from '../api.js'
import Rules from './Rules.jsx'
import Sales from './Sales.jsx'
import Insights from './Insights.jsx'
import Schedule from './Schedule.jsx'
import { Blocked, Msg } from './Ai.jsx'

// هر کانال قابلیت‌های خودش را دارد؛ هسته‌ی مرکزی (مغز، دانش، هوش مصنوعی) مشترک است
const SUBS = {
  instagram: [['connect', 'اتصال و وضعیت'], ['dm', 'دایرکت'], ['sales', 'فروش'], ['comment', 'کامنت'], ['story', 'استوری'], ['schedule', 'انتشار'], ['media', 'پست و استوری'], ['insights', 'تحلیل محتوا'], ['rules', 'دستورها'], ['blocked', 'مسدودها']],
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

// پل Composio: خوانش کامنت و دایرکت هر دقیقه، تا اپ Meta خود پروژه وصل شود
function Bridge() {
  const [b, setB] = useState(null)
  const load = () => api.get('/api/comment-poll').then(setB).catch(() => {})
  useEffect(() => { load() }, [])
  if (!b?.active) return null
  const line = (name, st) => (
    <div className="row" style={{ padding: '6px 0' }}>
      <span>{name}</span>
      <span className={`pill ${st ? (st.ok ? 'good' : 'warn') : ''}`}>{st ? (st.ok ? `سالم · ${timeAgo(st.at)}` : 'خطا') : 'هنوز بررسی نشده'}</span>
    </div>
  )
  const err = [b.status, b.dm_status].find((x) => x && !x.ok)
  async function toggle(e) {
    const on = e.target.checked
    if (on && !window.confirm('از این لحظه ربات به دایرکت‌های تازه‌ی مشتری‌ها خودکار جواب می‌دهد (دستورها، موتور فهم و هوش مصنوعی طبق تنظیمات). اگر ابزار دیگری مثل وردست هم روشن است، ممکن است مشتری دو جواب بگیرد. روشن شود؟')) return
    await api.post('/api/comment-poll', { dm_reply: on })
    load()
  }
  return (
    <section className="card">
      <h2>اتصال موقت (Composio)</h2>
      <p className="muted">تا اپ Meta وصل شود، کامنت‌ها و دایرکت‌های تازه هر دقیقه از این راه خوانده می‌شوند.</p>
      <div className="list">
        {line('خوانش کامنت‌ها', b.status)}
        {line('خوانش دایرکت‌ها', b.dm_status)}
      </div>
      {err && <p className="err">{err.error}</p>}
      <label className="check" style={{ marginTop: 8 }}><input type="checkbox" checked={!!b.dm_reply} onChange={toggle} /> جواب خودکار به دایرکت‌ها</label>
      <p className="hint muted">خاموش: دایرکت‌ها فقط در «صندوق» دیده می‌شوند و خودتان جواب می‌دهید. دستورهای کامنت همیشه کار می‌کنند.</p>
    </section>
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

      {id === 'instagram' && <Bridge />}

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

function Media() {
  const [d, setD] = useState(null)
  const [msg, setMsg] = useState(null)
  const [edit, setEdit] = useState({})
  useEffect(() => { api.get('/api/instagram/media-notes').then(setD).catch((e) => setMsg({ ok: false, text: e.message })) }, [])
  if (!d) return msg ? <Msg m={msg} /> : <div className="empty">در حال بارگذاری…</div>

  async function save(m, kind) {
    const v = edit[m.id] || { note: m.note, product: m.product }
    try { await api.put(`/api/instagram/media-notes/${m.id}`, { ...v, kind }); m.note = v.note; m.product = v.product; setMsg({ ok: true, text: 'ذخیره شد ✅' }) }
    catch (ex) { setMsg({ ok: false, text: ex.message }) }
  }
  const card = (m, kind) => {
    const v = edit[m.id] || { note: m.note || '', product: m.product || '' }
    const set = (patch) => setEdit({ ...edit, [m.id]: { ...v, ...patch } })
    return (
      <div key={m.id} className="item" style={{ cursor: 'default' }}>
        <div className="row" style={{ alignItems: 'flex-start', gap: 10 }}>
          <img src={m.thumbnail_url || m.media_url} alt="" loading="lazy" style={{ width: 72, height: 72, objectFit: 'cover', borderRadius: 8, flex: 'none' }} />
          <div style={{ flex: 1 }}>
            <p className="muted" style={{ margin: 0, fontSize: 12 }}>{(m.caption || '').slice(0, 90)}</p>
            <input type="text" value={v.product} placeholder="محصول، مثلاً: آیفون ۱۲" onChange={(e) => set({ product: e.target.value })} style={{ marginTop: 4 }} />
            <input type="text" value={v.note} placeholder="یادداشت برای ربات: حافظه، قیمت، شرایط…" onChange={(e) => set({ note: e.target.value })} style={{ marginTop: 4 }} />
            {(v.note !== (m.note || '') || v.product !== (m.product || '')) && <button className="btn sm primary" style={{ marginTop: 4 }} onClick={() => save(m, kind)}>ذخیره</button>}
          </div>
        </div>
      </div>
    )
  }
  return (
    <>
      <p className="muted">برای هر پست یا استوری بنویسید درباره‌ی کدام محصول است. وقتی کسی زیر آن کامنت بگذارد یا روی استوری جواب بدهد (مثلاً «قیمتش چنده؟»)، ربات می‌داند منظورش کدام محصول است و از فهرست کالای سایت جواب درست می‌دهد.</p>
      <Msg m={msg} />
      {!d.connected && <p className="err">اینستاگرام هنوز وصل نیست؛ بعد از اتصال، پست‌ها و استوری‌ها اینجا نشان داده می‌شوند.</p>}
      {d.error && <p className="err">{d.error}</p>}
      {d.stories.length > 0 && <h2>استوری‌های فعال</h2>}
      <div className="list">{d.stories.map((m) => card(m, 'story'))}</div>
      {d.posts.length > 0 && <h2 style={{ marginTop: 14 }}>پست‌ها</h2>}
      <div className="list">{d.posts.map((m) => card(m, 'post'))}</div>
    </>
  )
}

function IgPart({ part }) {
  const [s, setS] = useState(null)
  const [msg, setMsg] = useState(null)
  useEffect(() => { api.get('/api/ai/settings').then((r) => setS(r.settings)).catch(() => {}) }, [])
  if (!s) return <div className="empty">در حال بارگذاری…</div>
  const set = (patch) => setS({ ...s, ...patch })
  const KEYS = {
    dm: ['dm_enabled', 'prompt_dm', 'welcome_text', 'quick_replies_enabled', 'dm_quick_replies', 'typing_indicator', 'human_pause_minutes', 'batch_wait_seconds', 'notify_telegram'],
    comment: ['comment_enabled', 'comment_mode', 'public_ack', 'public_prices', 'prompt_comment', 'mod_profanity', 'mod_links', 'mod_words'],
    story: ['mention_reply_enabled', 'mention_replies'],
  }[part]
  const lines = (v) => (v || []).join('\n')
  const split = (v) => v.split('\n')

  async function applyIce() {
    setMsg(null)
    try { await api.post('/api/instagram/ice-breakers', { questions: (s.ice_breakers || []).filter((x) => x.trim()) }); setMsg({ ok: true, text: 'در اینستاگرام ثبت شد ✅' }) }
    catch (ex) { setMsg({ ok: ex.status === 409, text: ex.message }) }
  }

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
          <label className="check"><input type="checkbox" checked={s.typing_indicator} onChange={(e) => set({ typing_indicator: e.target.checked })} /> پیش از جواب «دیده شد» و «در حال نوشتن…» نشان بدهد</label>
        </section>
      )}
      {part === 'dm' && (
        <section className="card">
          <h2>همکار و ربات</h2>
          <div className="field">
            <label>توقف ربات بعد از جواب همکار (دقیقه، ۰ = خاموش)</label>
            <input type="number" min="0" max="1440" value={s.human_pause_minutes} onChange={(e) => set({ human_pause_minutes: Number(e.target.value) })} />
            <p className="hint muted">وقتی شما از پنل یا از خود اپ اینستاگرام به کسی جواب بدهید، ربات تا این مدت برای همان نفر ساکت می‌ماند تا گفتگو را ادامه دهید. هر جواب تازه زمان را از نو می‌شمارد. در صفحه‌ی گفتگو دکمه‌ی «برگرداندن به ربات» هست. ⚠️ تا وقتی ابزار دیگری (مثل وردست) به پیج وصل است، جواب‌های آن هم «جواب همکار» حساب می‌شود.</p>
          </div>
          <div className="field">
            <label>انتظار برای چند پیام پشت‌سرهم (ثانیه، ۰ = خاموش)</label>
            <input type="number" min="0" max="120" value={s.batch_wait_seconds} onChange={(e) => set({ batch_wait_seconds: Number(e.target.value) })} />
            <p className="hint muted">ربات بعد از آخرین پیام مشتری این‌قدر صبر می‌کند و به همه‌ی پیام‌هایی که در این فاصله فرستاده یک جواب می‌دهد. برای مشتری‌هایی که سؤالشان را در چند پیام کوتاه می‌نویسند، ۱۰ تا ۲۰ ثانیه مناسب است.</p>
          </div>
          <label className="check"><input type="checkbox" checked={s.notify_telegram} onChange={(e) => set({ notify_telegram: e.target.checked })} /> ارجاع‌ها به گروه پشتیبانی تلگرام هم برود (تاپیک «📸 اینستاگرام»)</label>
        </section>
      )}
      {part === 'dm' && (
        <section className="card">
          <h2>پیام خوش‌آمد</h2>
          <p className="muted">فقط برای اولین دایرکت هر مشتری، پیش از جواب اصلی. خالی یعنی خاموش.</p>
          <textarea rows={3} value={s.welcome_text} placeholder="سلام، به استوک لند خوش اومدید 🌸 هر سؤالی دارید بپرسید؛ قیمت، اقساط، گارانتی…" onChange={(e) => set({ welcome_text: e.target.value })} />
        </section>
      )}
      {part === 'dm' && (
        <section className="card">
          <h2>دکمه‌های پاسخ سریع</h2>
          <label className="check"><input type="checkbox" checked={s.quick_replies_enabled} onChange={(e) => set({ quick_replies_enabled: e.target.checked })} /> زیر جواب‌های ربات دکمه نشان بدهد</label>
          <div className="field">
            <label>دکمه‌ها (هر خط یکی، حداکثر ۱۳، هر کدام تا ۲۰ نویسه)</label>
            <textarea rows={4} value={lines(s.dm_quick_replies)} onChange={(e) => set({ dm_quick_replies: split(e.target.value) })} />
            <p className="hint muted">لمس هر دکمه همان متن را از طرف مشتری می‌فرستد و ربات جوابش را می‌دهد. برای دستورهای کلمه‌ای، دکمه‌ی جدا در فرم همان دستور تعریف می‌شود.</p>
          </div>
        </section>
      )}
      {part === 'dm' && (
        <section className="card">
          <h2>سؤال‌های شروع گفتگو</h2>
          <p className="muted">وقتی کسی برای اولین بار دایرکت پیج را باز می‌کند، این سؤال‌ها (حداکثر ۴) را می‌بیند و با یک لمس می‌پرسد.</p>
          <textarea rows={4} value={lines(s.ice_breakers)} onChange={(e) => set({ ice_breakers: split(e.target.value) })} />
          <button type="button" className="btn" style={{ marginTop: 6 }} onClick={applyIce}>ذخیره و ثبت در اینستاگرام</button>
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
      {part === 'comment' && (
        <section className="card">
          <h2>نظارت خودکار کامنت</h2>
          <p className="muted">کامنت مشکل‌دار مخفی می‌شود (فقط نویسنده و دوستانش می‌بینند) و جواب نمی‌گیرد. در «صندوق ← کامنت‌ها» با یک لمس برمی‌گردد.</p>
          <label className="check"><input type="checkbox" checked={s.mod_profanity} onChange={(e) => set({ mod_profanity: e.target.checked })} /> کامنت توهین‌آمیز و فحش</label>
          <label className="check"><input type="checkbox" checked={s.mod_links} onChange={(e) => set({ mod_links: e.target.checked })} /> کامنت دارای لینک یا آدرس سایت (تبلیغ پیج‌های دیگر)</label>
          <div className="field">
            <label>کلمه‌های ممنوع (هر خط یکی)</label>
            <textarea rows={3} value={lines(s.mod_words)} placeholder={'نام پیج رقیب\nکلمه‌ی تبلیغاتی'} onChange={(e) => set({ mod_words: split(e.target.value) })} />
          </div>
        </section>
      )}
      {part === 'story' && (
        <section className="card">
          <h2>منشن در استوری</h2>
          <p className="muted">وقتی کسی پیج را در استوری‌اش منشن کند.</p>
          <label className="check"><input type="checkbox" checked={s.mention_reply_enabled} onChange={(e) => set({ mention_reply_enabled: e.target.checked })} /> در دایرکت تشکر کند</label>
          <div className="field">
            <label>متن‌های تشکر (هر خط یکی، به نوبت)</label>
            <textarea rows={3} value={lines(s.mention_replies)} onChange={(e) => set({ mention_replies: split(e.target.value) })} />
          </div>
          <p className="hint muted">برای جواب متفاوت، در «دستورها» دستوری با محل دریافت «منشن در استوری» بسازید؛ دستور اولویت دارد.</p>
        </section>
      )}
      {part === 'story' && (
        <section className="card">
          <h2>جواب به استوری</h2>
          <p className="muted">وقتی مشتری روی یکی از استوری‌ها جواب می‌دهد، مثل دایرکت جواب داده می‌شود؛ مغز مرکزی می‌داند پیام درباره‌ی استوری است و اگر معلوم نباشد کدام محصول، می‌پرسد. دستور مخصوص هم با محل دریافت «جواب به استوری» ساخته می‌شود.</p>
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
      {cur === 'sales' && <Sales />}
      {cur === 'comment' && <IgPart part="comment" />}
      {cur === 'story' && <IgPart part="story" />}
      {cur === 'schedule' && <Schedule />}
      {cur === 'media' && <Media />}
      {cur === 'insights' && <Insights />}
      {cur === 'rules' && <Rules embedded />}
      {cur === 'blocked' && <Blocked />}
    </>
  )
}
