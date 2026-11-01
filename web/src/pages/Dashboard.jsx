import React from 'react'
import { fa, pct, timeAgo, usd } from '../api.js'

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
                <span><span className={`pill ${r.ok ? 'good' : 'warn'}`}>{{ public: 'کامنت', private: 'دایرکت خصوصی', dm: 'دایرکت' }[r.kind]}</span> {r.rule_id ? '' : <span className="pill muted">دستی</span>}</span>
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
