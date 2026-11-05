import React, { useEffect, useState } from 'react'
import { api, fa, timeAgo } from '../api.js'
import { Msg } from './Ai.jsx'

const KIND = { REEL: 'ریلز', IMAGE: 'عکس', CAROUSEL_ALBUM: 'کاروسل', VIDEO: 'ویدیو' }
const pct = (v) => (v === null || v === undefined ? '—' : `${fa(v)}٪`)
const hm = (ts) => new Date(ts * 1000).toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Tehran' })

// تحلیل محتوا: آمار استوری (پیش از پایان ۲۴ ساعت ذخیره می‌شود)، ریلز و پست؛ فقط خواندن
export default function Insights() {
  const [days, setDays] = useState(14)
  const [d, setD] = useState(null)
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState(false)
  const load = () => api.get(`/api/insights?days=${days}`).then(setD).catch((e) => setMsg({ ok: false, text: e.message }))
  useEffect(() => { load() }, [days])

  async function collect() {
    setBusy(true); setMsg(null)
    try {
      const r = await api.post('/api/insights/collect')
      setMsg({ ok: true, text: `گرفته شد ✅ ${fa(r.stories.count)} استوری زنده و ${fa(r.media.count)} پست (${r.stories.source})` })
      load()
    } catch (ex) { setMsg({ ok: false, text: ex.message }) }
    setBusy(false)
  }

  if (!d) return msg ? <Msg m={msg} /> : <div className="empty">در حال بارگذاری…</div>
  const st = d.status || {}
  const err = [st.stories, st.media].find((x) => x && !x.ok)
  return (
    <>
      <section className="card">
        <div className="row-between">
          <h2 style={{ margin: 0 }}>تحلیل محتوا</h2>
          <span className="actions">
            {[7, 14, 30].map((n) => <button key={n} className={`chip ${days === n ? 'active' : ''}`} onClick={() => setDays(n)}>{fa(n)} روز</button>)}
            <button className="btn sm" disabled={busy || !d.source} onClick={collect}>{busy ? 'در حال گرفتن…' : 'بگیر همین الان'}</button>
          </span>
        </div>
        <p className="muted">
          {d.source ? `منبع: ${d.source}. ` : 'منبع آمار تنظیم نیست: کلید Composio (همان ck_… از dashboard.composio.dev) را در «مغز مرکزی ← تنظیمات مغز ← کلید سرویس‌ها» ثبت کنید. '}
          آمار هر استوری فقط تا ۲۴ ساعت در اینستاگرام هست؛ هر ۹۰ دقیقه خودکار ذخیره می‌شود.
          {d.last_capture ? ` آخرین ذخیره: ${timeAgo(d.last_capture)}.` : ''}
        </p>
        {err && <p className="err">آخرین تلاش ناموفق بود: {err.error}</p>}
        <Msg m={msg} />
      </section>

      <section className="card">
        <h3>استوری</h3>
        {!d.stories.length ? <div className="empty">هنوز آماری ذخیره نشده.</div> : (
          <>
            <div className="tiles">
              <div className="tile"><b>{fa(d.stories.length)}</b><span>استوری</span></div>
              <div className="tile"><b>{fa(d.story_avg.views)}</b><span>میانگین ویو هر استوری</span></div>
              <div className="tile"><b>{pct(d.story_avg.skip_pct)}</b><span>رد کردن (میانه)</span></div>
              <div className="tile"><b>{pct(d.story_avg.exit_pct)}</b><span>خروج (میانه)</span></div>
              <div className="tile"><b>{fa(d.story_avg.replies_per_1k)}</b><span>ریپلای در هر ۱۰۰۰ ویو</span></div>
              <div className="tile"><b>{fa(d.story_totals.profile_visits)}</b><span>رفتن به پروفایل</span></div>
            </div>
            <h4>روزها</h4>
            <p className="muted">«ماندگاری» یعنی آخرین استوری روز به چند درصدِ کسانی رسید که اولی را دیدند.</p>
            <div className="list">
              {d.story_days.map((x) => (
                <div key={x.day} className="item"><div className="row-between">
                  <span>{new Date(x.day).toLocaleDateString('fa-IR', { weekday: 'long', month: 'long', day: 'numeric' })} · {fa(x.count)} استوری</span>
                  <span className="muted">ویو {fa(x.views)} · ریپلای {fa(x.replies)} · ماندگاری {pct(x.keep_pct)}</span>
                </div></div>
              ))}
            </div>
            <h4>هر استوری</h4>
            <div className="list">
              {d.stories.map((s) => (
                <a key={s.id} className="item" href={s.permalink} target="_blank" rel="noreferrer">
                  <div className="row-between">
                    <span>{hm(s.posted_at)} · {s.type === 'VIDEO' ? 'ویدیو' : 'عکس'} {!s.final && <span className="pill warn">هنوز زنده</span>}</span>
                    <span className="muted">ویو {fa(s.views)} · ریچ {fa(s.reach)}</span>
                  </div>
                  <div className="muted" style={{ marginTop: 4 }}>
                    رد {pct(s.skip_pct)} · خروج {pct(s.exit_pct)} · ریپلای {fa(s.replies)} · اشتراک {fa(s.shares)} · پروفایل {fa(s.profile_visits)} · فالو {fa(s.follows)}
                  </div>
                </a>
              ))}
            </div>
          </>
        )}
      </section>

      <section className="card">
        <h3>ریلز و پست</h3>
        {!Object.keys(d.kinds).length ? <div className="empty">هنوز آماری ذخیره نشده.</div> : (
          <>
            <div className="list">
              {Object.entries(d.kinds).map(([k, v]) => (
                <div key={k} className="item"><div className="row-between">
                  <span>{KIND[k] || k} · {fa(v.count)} مورد</span>
                  <span className="muted">
                    ریچ میانه {fa(v.median_reach)} · ذخیره {fa(v.saves_per_1k)} و اشتراک {fa(v.shares_per_1k)} در هر ۱۰۰۰
                    {v.median_skip !== null && ` · رد شدن ${pct(v.median_skip)} · تماشا ${fa(v.median_watch_s)} ثانیه`}
                  </span>
                </div></div>
              ))}
            </div>
            <h4>بیشترین دیده‌شدن</h4>
            <MediaList items={d.top} />
            <h4>بیشترین ذخیره و اشتراک (به نسبت دیده‌شدن)</h4>
            <p className="muted">محتوایی که مردم نگه می‌دارند و برای دیگران می‌فرستند؛ الگوی ریلزهای بعدی.</p>
            <MediaList items={d.valuable} extra />
          </>
        )}
      </section>
    </>
  )
}

function MediaList({ items, extra }) {
  return (
    <div className="list">
      {items.map((m) => (
        <a key={m.id} className="item" href={m.permalink} target="_blank" rel="noreferrer">
          <div className="row-between">
            <span>{KIND[m.kind] || m.kind} · {m.caption || '—'}</span>
            <span className="muted">{timeAgo(m.posted_at)}</span>
          </div>
          <div className="muted" style={{ marginTop: 4 }}>
            ریچ {fa(m.reach)} · ذخیره {fa(m.saved)} · اشتراک {fa(m.shares)} · کامنت {fa(m.comments)}
            {m.reels_skip_rate !== undefined && ` · رد شدن ${pct(m.reels_skip_rate)}`}
            {extra && ` · ${fa(m.value_per_1k)} در هر ۱۰۰۰`}
          </div>
        </a>
      ))}
    </div>
  )
}
