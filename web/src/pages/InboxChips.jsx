import React from 'react'

// صندوق پیام: هر کانال بخش خودش را دارد. پیام‌های تلگرام در گروه پشتیبانی تیم (تاپیک هر مشتری) است.
export default function InboxChips({ cur }) {
  return (
    <div className="chips">
      <a href="#/comments" className={`chip ${cur === 'comments' ? 'active' : ''}`}>کامنت‌های اینستاگرام</a>
      <a href="#/messages" className={`chip ${cur === 'messages' ? 'active' : ''}`}>دایرکت اینستاگرام</a>
      <a href="#/customers" className={`chip ${cur === 'customers' ? 'active' : ''}`}>مشتری‌ها</a>
      <a href="#/customers/lost" className={`chip ${cur === 'lost' ? 'active' : ''}`}>فرصت‌های ازدست‌رفته</a>
      <a href="#/orders" className={`chip ${cur === 'orders' ? 'active' : ''}`}>سفارش‌ها</a>
    </div>
  )
}
