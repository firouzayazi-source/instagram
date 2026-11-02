import React, { useEffect, useState } from 'react'
import { api, fa, pct, timeAgo, usd } from '../api.js'

function Reports() {
  const [r, setR] = useState(null)
  const [days, setDays] = useState(30)
  useEffect(() => { api.get(`/api/reports?days=${days}`).then(setR).catch(() => {}) }, [days])
  if (!r) return null
  const total = r.replies.bot + r.replies.admin
  const max = Math.max(1, ...r.series.map((x) => Math.max(x.bot + x.admin, x.incoming)))
  return (
    <section className="card">
      <div className="row-between">
        <h2 style={{ margin: 0 }}>گزارش</h2>
        <div className="actions">{[[7, '۷ روز'], [30, '۳۰ روز'], [90, '۹۰ روز']].map(([k, l]) => <button key={k} className={`chip ${days === k ? 'active' : ''}`} onClick={() => setDays(k)}>{l}</button>)}</div>
      </div>
      <h3 style={{ margin: '12px 0 6px', fontSize: 15 }}>چه کسی به مشتری‌ها جواب می‌دهد؟</h3>
      <p className="muted" style={{ margin: 0 }}>{fa(total)} جواب · سهم ربات و دستورها {fa(r.replies.bot_pct)}٪</p>
      {[['ربات و دستورها', r.replies.bot], ['همکار (پنل و اپ اینستاگرام)', r.replies.admin]].map(([l, n]) => (
        <div key={l} style={{ marginTop: 8 }}>
          <div className="row"><span>{l}</span><b>{fa(n)} ({fa(total ? Math.round((n * 100) / total) : 0)}٪)</b></div>
          <div style={{ height: 8, borderRadius: 4, background: 'var(--line, #e5e7eb)', overflow: 'hidden' }}><div style={{ width: `${total ? (n * 100) / total : 0}%`, height: '100%', background: 'var(--accent, #2563eb)' }} /></div>
        </div>
      ))}
      <div className="tiles" style={{ marginTop: 12 }}>
        <div className="tile"><b>{fa(r.incoming)}</b><span>پیام و کامنت دریافتی</span></div>
        <div className="tile"><b>{r.out_of_hours.pct === null ? '—' : `${fa(r.out_of_hours.pct)}٪`}</b><span>بیرون از ساعت کاری</span></div>
        <a href="#/messages" className={`tile ${r.waiting_open ? 'warn' : ''}`}><b>{fa(r.waiting_open)}</b><span>منتظر جواب (هنوز می‌شود جواب داد)</span></a>
        <div className={`tile ${r.waiting_24h ? 'bad' : ''}`}><b>{fa(r.waiting_24h)}</b><span>بیش از ۲۴ ساعت منتظر مانده</span></div>
        <a href="#/customers" className="tile"><b>{fa(r.customers_new)}</b><span>مشتری تازه (از {fa(r.customers_total)})</span></a>
        <div className="tile"><b>{r.followers === null || r.followers === undefined ? '—' : fa(r.followers)}</b><span>فالوور</span></div>
      </div>
      {Object.keys(r.tags).length > 0 && (
        <p className="muted" style={{ marginTop: 8 }}>{Object.entries(r.tags).map(([t, n]) => `${t}: ${fa(n)}`).join(' · ')}</p>
      )}
      <h3 style={{ margin: '12px 0 6px', fontSize: 15 }}>۱۴ روز اخیر</h3>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 80 }} aria-label="نمودار ۱۴ روز">
        {r.series.map((x, i) => (
          <div key={i} title={`دریافتی ${x.incoming} · ربات ${x.bot} · همکار ${x.admin}`} style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', height: '100%' }}>
            <div style={{ height: `${(x.admin * 100) / max}%`, background: 'var(--warn, #f59e0b)' }} />
            <div style={{ height: `${(x.bot * 100) / max}%`, background: 'var(--accent, #2563eb)' }} />
          </div>
        ))}
      </div>
      <p className="muted" style={{ fontSize: 12 }}>آبی: ربات و دستورها · نارنجی: همکار</p>
    </section>
  )
}

export default function Dashboard({ stats: s }) {
  const days = s.token_expires_at ? Math.floor((s.token_expires_at - Date.now() / 1000) / 86400) : null
  return (
    <>
      <header className="topbar"><h1>پیشخوان</h1><span className="sub">stock_land.ir</span></header>
      <section className="card">
        <h2>۲۴ ساعت گذشته</h2>
        <div className="tiles">
          <div className="tile good"><b>{fa(s.replies_ok_24h)}</b><span>پاسخ خودکار ارسال‌شده</span></div>
          <div className={`tile ${s.replies_failed_24h ? 'bad' : ''}`}><b>{fa(s.replies_failed_24h)}</b><span>ارسال ناموفق</span></div>
          <div className="tile"><b>{fa(s.comments_24h)}</b><span>کامنت دریافتی</span></div>
          <div className="tile"><b>{fa(s.rules_enabled)}</b><span>قانون فعال</span></div>
        </div>
      </section>
      <section className="card">
        <h2>پاسخ خودکار</h2>
        <div className="tiles">
          <div className="tile good"><b>{pct(s.auto_answered_24h, s.incoming_24h)}</b><span>نرخ پاسخ خودکار ({fa(s.auto_answered_24h)} از {fa(s.incoming_24h)})</span></div>
          <div className="tile"><b>{fa(s.ai?.replies_24h)}</b><span>پاسخ هوشمند ۲۴ ساعت</span></div>
          <a href="#/ai/handoffs" className={`tile ${s.ai?.handoffs_open ? 'warn' : ''}`}><b>{fa(s.ai?.handoffs_open)}</b><span>ارجاع باز به شما</span></a>
          <a href="#/ai" className="tile"><b>{usd(s.ai?.cost_month)}</b><span>هزینه‌ی هوش مصنوعی این ماه {s.ai && !s.ai.enabled ? '(خاموش)' : ''}</span></a>
        </div>
      </section>
      <Reports />
      <section className="card">
        <h2>نیاز به توجه</h2>
        <div className="tiles">
          <a href="#/comments" className={`tile ${s.comments_unanswered ? 'warn' : ''}`}><b>{fa(s.comments_unanswered)}</b><span>کامنت بی‌پاسخ</span></a>
          <a href="#/messages" className={`tile ${s.conversations_unanswered ? 'warn' : ''}`}><b>{fa(s.conversations_unanswered)}</b><span>دایرکت بی‌پاسخ</span></a>
          <div className={`tile ${s.events_error ? 'bad' : ''}`}><b>{fa(s.events_error)}</b><span>رویداد با خطا</span></div>
          <div className={`tile ${days !== null && days < 10 ? 'bad' : ''}`}><b>{days === null ? '—' : fa(days)}</b><span>روز تا انقضای توکن</span></div>
        </div>
      </section>
      <section className="card">
        <h2>آخرین پاسخ‌ها</h2>
        {!s.recent?.length && <p className="muted">هنوز پاسخی ارسال نشده.</p>}
        <div className="list">
          {(s.recent || []).map((r) => (
            <div key={r.id} className="item" style={{ cursor: 'default' }}>
              <div className="row">
                <span><span className={`pill ${r.ok ? 'good' : 'warn'}`}>{{ public: 'کامنت', private: 'دایرکت خصوصی', dm: 'دایرکت' }[r.kind]}</span> {(r.event_id || '').startsWith('manual:') ? <span className="pill muted">همکار</span> : r.rule_id ? <span className="pill muted">دستور</span> : <span className="pill muted">مغز مرکزی</span>}</span>
                <span className="when">{timeAgo(r.created_at)}</span>
              </div>
              <div className="text">{r.text}</div>
              {!r.ok && <div className="err">{r.error}</div>}
            </div>
          ))}
        </div>
      </section>
    </>
  )
}
