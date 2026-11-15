import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './styles.css'

// صفحه‌ی انتظار (index.html): وقتی برنامه آماده شد (App صدا می‌زند) آرام محو می‌شود؛ دست‌کم ۰.۶ ثانیه تا
// انیمیشن لوگو نیمه‌کاره قطع نشود، و حداکثر ۱۲ ثانیه تا اگر چیزی گیر کرد صفحه پشتش نماند
let splashGone = false
window.hideSplash = () => {
  if (splashGone) return
  splashGone = true
  const el = document.getElementById('splash')
  if (!el) return
  setTimeout(() => {
    el.classList.add('out')
    setTimeout(() => { el.remove(); document.documentElement.style.background = 'var(--bg)' }, 400)
  }, Math.max(0, 600 - performance.now()))
}
setTimeout(() => window.hideSplash(), 12000)

createRoot(document.getElementById('root')).render(<App />)

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}))
}

// آیفون در حالت اپ گاهی با دو انگشت زوم می‌کند و منوی پایین از جا درمی‌رود (دو ضربه را CSS می‌بندد)
document.addEventListener('gesturestart', (e) => e.preventDefault())
