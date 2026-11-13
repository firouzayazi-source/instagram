import React from 'react'
import Icon from '../icons.jsx'

const GROUPS = [
  ['کسب‌وکار', [
    ['#/customers', 'users', 'مشتری‌ها', 'پرونده‌ی هر مشتری و برچسب‌ها'],
    ['#/smart/phones', 'link', 'خروجی شماره‌ها', 'شماره‌ی مشتری‌ها، تماس و خروجی اکسل'],
    ['#/customers/lost', 'target', 'فرصت‌های ازدست‌رفته', 'کسانی که قیمت پرسیدند و نخریدند'],
    ['#/orders', 'cart', 'سفارش‌ها', 'سفارش‌های دایرکت و تلگرام'],
  ]],
  ['هوش و دانش', [
    ['#/ai', 'sparkle', 'مغز مرکزی', 'دانش، هوش مصنوعی و کلیدها'],
    ['#/ai/handoffs', 'hand', 'ارجاع‌ها به همکار', 'پیام‌هایی که ربات به شما سپرد'],
  ]],
  ['اتصال و تنظیمات', [
    ['#/channels/instagram/connect', 'insta', 'اینستاگرام', 'وضعیت اتصال، خوانش کامنت و دایرکت'],
    ['#/channels/telegram', 'link', 'ربات تلگرام', 'وضعیت و هوش مصنوعی تلگرام'],
    ['#/channels/instagram/comment', 'comment', 'تنظیمات کامنت و نظارت', 'مخفی کردن کامنت نامناسب'],
    ['#/channels/instagram/dm', 'dm', 'تنظیمات دایرکت', 'پیام خوش‌آمد، دکمه‌های پاسخ سریع'],
    ['#/channels/instagram/sales', 'cart', 'فروش در دایرکت', 'کارت محصول و ثبت سفارش'],
    ['#/channels/instagram/blocked', 'user', 'مسدودها', 'کاربرانی که جواب نمی‌گیرند'],
    ['#/settings', 'gear', 'حساب و رمز', 'رمز پنل، اعلان‌ها، خروج'],
  ]],
]

export default function More() {
  return (
    <>
      <header className="topbar"><div className="title"><h1>بیشتر</h1><span className="sub">همه‌ی بخش‌ها و تنظیمات</span></div></header>
      {GROUPS.map(([title, rows]) => (
        <section key={title} className="sec">
          <div className="sec-h"><div className="grow"><h2>{title}</h2></div></div>
          <div style={{ borderTop: '1px solid var(--line)' }}>
            {rows.map(([href, ic, t, d]) => (
              <a key={href} href={href} className="menu-row">
                <span className="ico"><Icon n={ic} /></span>
                <span className="grow"><b>{t}</b><small>{d}</small></span>
                <span style={{ width: 20, height: 20, color: 'var(--muted)' }}><Icon n="chevL" /></span>
              </a>
            ))}
          </div>
        </section>
      ))}
    </>
  )
}
