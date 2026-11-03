import React, { useEffect, useState } from 'react'
import { api, timeAgo } from '../api.js'
import { Msg } from './Ai.jsx'

const KEYS = ['showcase_cards', 'order_enabled', 'order_payment_text']

// فروش در دایرکت: کارت ویترین، گرفتن سفارش و رسید، و وبهوک لید/سفارش
export default function Sales() {
  const [s, setS] = useState(null)
  const [hook, setHook] = useState(null)
  const [secret, setSecret] = useState('')
  const [msg, setMsg] = useState(null)
  const [hmsg, setHmsg] = useState(null)
  useEffect(() => {
    api.get('/api/ai/settings').then((r) => setS(r.settings)).catch(() => {})
    api.get('/api/webhook').then(setHook).catch(() => {})
  }, [])
  if (!s || !hook) return <div className="empty">در حال بارگذاری…</div>
  const set = (patch) => setS({ ...s, ...patch })

  async function save(e) {
    e.preventDefault(); setMsg(null)
    try { const r = await api.put('/api/ai/settings', Object.fromEntries(KEYS.map((k) => [k, s[k]]))); setS(r.settings); setMsg({ ok: true, text: 'ذخیره شد ✅' }) }
    catch (ex) { setMsg({ ok: false, text: ex.message }) }
  }

  async function saveHook(e) {
    e.preventDefault(); setHmsg(null)
    try {
      setHook(await api.put('/api/webhook', { url: hook.url, events: hook.events, ...(secret ? { secret } : {}) }))
      setSecret(''); setHmsg({ ok: true, text: 'ذخیره شد ✅' })
    } catch (ex) { setHmsg({ ok: false, text: ex.message }) }
  }

  async function testHook() {
    setHmsg(null)
    try {
      const r = await api.post('/api/webhook/test')
      setHmsg({ ok: r.ok, text: r.ok ? 'گیرنده پیام آزمایشی را گرفت ✅' : 'گیرنده جواب نداد یا خطا داد' })
      setHook(await api.get('/api/webhook'))
    } catch (ex) { setHmsg({ ok: false, text: ex.message }) }
  }

  return (
    <>
      <form onSubmit={save}>
        <section className="card">
          <h2>ویترین محصول</h2>
          <label className="check"><input type="checkbox" checked={s.showcase_cards} onChange={(e) => set({ showcase_cards: e.target.checked })} /> موجودی‌ها به‌شکل کارت با عکس، قیمت و دکمه‌ی «مشاهده در سایت» و «🛒 سفارش» برود</label>
          <p className="hint muted">وقتی مشتری قیمت یا موجودی مدلی را می‌پرسد، موتور فهم از فهرست کالای سایت تا ۱۰ کارت می‌فرستد که مشتری ورق می‌زند. اگر اینستاگرام کارت را نپذیرد، همان فهرست متنی می‌رود.</p>
        </section>
        <section className="card">
          <h2>گرفتن سفارش در دایرکت</h2>
          <label className="check"><input type="checkbox" checked={s.order_enabled} onChange={(e) => set({ order_enabled: e.target.checked })} /> ربات سفارش بگیرد</label>
          <p className="hint muted">با لمس «🛒 سفارش» زیر کارت، یا پیامی مثل «ثبت سفارش» و «می‌خوام بخرم ۱۳ پرو»، ربات قدم‌به‌قدم نام، شماره، شهر و آدرس را می‌پرسد (چیزی که در پرونده‌ی مشتری هست دوباره پرسیده نمی‌شود)، خلاصه را برای تأیید نشان می‌دهد و سفارش را ثبت می‌کند. «لغو» هر جا گفتگو را می‌بندد. سفارش تازه در «صندوق ← سفارش‌ها»، پوش و تاپیک «📸 اینستاگرام» گروه تلگرام دیده می‌شود.</p>
          <div className="field">
            <label>روش پرداخت (بعد از ثبت به مشتری گفته می‌شود)</label>
            <textarea rows={3} value={s.order_payment_text} placeholder={'مبلغ را به کارت ۶۰۳۷-…-…-… به نام … واریز کنید.'} onChange={(e) => set({ order_payment_text: e.target.value })} />
            <p className="hint muted">اگر پر باشد، ربات از مشتری عکس رسید می‌خواهد؛ عکسی که تا ۳ روز بفرستد رسید همان سفارش ثبت می‌شود و با عکس به گروه تلگرام می‌رود. خالی یعنی «همکارم برای هماهنگی پرداخت پیام می‌ده».</p>
          </div>
        </section>
        <Msg m={msg} />
        <div className="actions"><button className="btn primary">ذخیره</button><a className="btn" href="#/orders">سفارش‌ها</a></div>
      </form>

      <form className="card" onSubmit={saveHook} style={{ marginTop: 12 }}>
        <h2>وبهوک لید و سفارش</h2>
        <p className="muted">شماره‌ی تازه‌ی مشتری و هر سفارش (و تغییر وضعیتش) با POST به این آدرس فرستاده می‌شود؛ مثلاً برای حساب‌لند یا یک CRM. سربرگ <code>X-Igbot-Signature</code> برابر <code>sha256=HMAC(رمز، بدنه)</code> است.</p>
        <div className="field"><label>آدرس (https)</label><input type="text" dir="ltr" value={hook.url} placeholder="https://…" onChange={(e) => setHook({ ...hook, url: e.target.value })} /></div>
        <div className="field">
          <label>رمز امضا {hook.secret_set ? '(تنظیم شده؛ برای عوض کردن رمز تازه بنویسید)' : ''}</label>
          <input type="password" dir="ltr" value={secret} autoComplete="new-password" onChange={(e) => setSecret(e.target.value)} />
        </div>
        <div className="field">
          <label>رویدادها</label>
          {Object.entries(hook.all_events).map(([k, l]) => (
            <label key={k} className="check"><input type="checkbox" checked={hook.events.includes(k)}
              onChange={(e) => setHook({ ...hook, events: e.target.checked ? [...hook.events, k] : hook.events.filter((x) => x !== k) })} /> {l}</label>
          ))}
        </div>
        <Msg m={hmsg} />
        <div className="actions"><button className="btn primary">ذخیره</button><button type="button" className="btn" onClick={testHook}>پیام آزمایشی</button></div>
        {hook.log.length > 0 && (
          <div className="list" style={{ marginTop: 8 }}>
            {hook.log.slice(0, 8).map((x, i) => (
              <div key={i} className="row"><span><span className={`pill ${x.ok ? 'good' : 'bad'}`}>{x.ok ? 'رسید' : 'خطا'}</span> {x.event} · {x.info}</span><span className="when">{timeAgo(x.at)}</span></div>
            ))}
          </div>
        )}
      </form>
    </>
  )
}
