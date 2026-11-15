import React, { Suspense, lazy, useEffect, useState } from 'react'
import { api } from './api.js'
import Login from './pages/Login.jsx'
import Dashboard from './pages/Dashboard.jsx'
// بعد از انتشار تازه، صفحه‌ای که از نسخه‌ی قبلی در کش مانده ممکن است دنبال فایل قدیمی بگردد: یک بار تازه‌سازی
const lazyPage = (load) => lazy(() => load().then((m) => { sessionStorage.removeItem('chunk-reload'); return m }).catch((e) => {
  if (!sessionStorage.getItem('chunk-reload')) { sessionStorage.setItem('chunk-reload', '1'); location.reload() }
  throw e
}))
const Comments = lazyPage(() => import('./pages/Comments.jsx'))
const Messages = lazyPage(() => import('./pages/Messages.jsx'))
const Ai = lazyPage(() => import('./pages/Ai.jsx'))
const RuleForm = lazyPage(() => import('./pages/RuleForm.jsx'))
const Settings = lazyPage(() => import('./pages/Settings.jsx'))
const Channels = lazyPage(() => import('./pages/Channels.jsx'))
const Customers = lazyPage(() => import('./pages/Customers.jsx'))
const Orders = lazyPage(() => import('./pages/Orders.jsx'))
const Rules = lazyPage(() => import('./pages/Rules.jsx'))
const Content = lazyPage(() => import('./pages/Content.jsx'))
const More = lazyPage(() => import('./pages/More.jsx'))
const Smart = lazyPage(() => import('./pages/Smart.jsx'))
import Icon from './icons.jsx'

// پیشخوان و ورود همراه برنامه می‌آیند؛ بقیه‌ی صفحه‌ها فقط وقتی باز شوند (باز شدن سریع‌تر روی اینترنت کند)
const TABS = [
  ['/', 'پیشخوان', 'grid'],
  ['/content', 'محتوا', 'folder'],
  ['/rules', 'پاسخ هوشمند', 'bot'],
  ['/messages', 'پیام‌ها', 'inbox'],
  ['/comments', 'کامنت‌ها', 'comment'],
]

function useHashRoute() {
  const get = () => (location.hash.replace(/^#/, '') || '/')
  const [route, setRoute] = useState(get)
  useEffect(() => {
    const on = () => setRoute(get())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return route
}

export default function App() {
  const [authed, setAuthed] = useState(null)
  const [stats, setStats] = useState({})
  const route = useHashRoute()

  useEffect(() => {
    api.get('/api/me').then(() => setAuthed(true)).catch(() => setAuthed(false))
    const lost = () => setAuthed(false)
    window.addEventListener('auth:lost', lost)
    return () => window.removeEventListener('auth:lost', lost)
  }, [])

  useEffect(() => {
    if (!authed) return
    const load = () => api.get('/api/stats').then(setStats).catch(() => {})
    load()
    const t = setInterval(load, 30000)
    return () => clearInterval(t)
  }, [authed, route])

  if (authed === null) return <div className="empty">در حال بارگذاری…</div>
  if (!authed) return <Login onLogin={() => setAuthed(true)} />

  let page
  if (route === '/') page = <Dashboard stats={stats} />
  else if (route === '/comments') page = <Comments />
  else if (route.startsWith('/messages')) page = <Messages userId={route.split('/')[2] || null} />
  else if (route === '/rules' || route === '/ai/rules' || route === '/channels/instagram/rules') page = <Rules />
  else if (route.startsWith('/content')) page = <Content sub={route.split('/')[2]} />
  else if (route === '/more') page = <More />
  else if (route.startsWith('/smart')) page = <Smart sub={route.split('/')[2]} id={route.split('/')[3]} />
  else if (route === '/ai/products') page = <Smart sub="products" />
  else if (route.startsWith('/channels/instagram/') && ['schedule', 'ideas', 'insights', 'media'].includes(route.split('/')[3])) page = <Content sub={{ media: 'posts' }[route.split('/')[3]] || route.split('/')[3]} />
  else if (route === '/ai/blocked') page = <Channels id="instagram" sub="blocked" />
  else if (route.startsWith('/ai')) page = <Ai sub={route.split('/')[2]} badges={{ handoffs: stats.ai?.handoffs_open }} />
  else if (route.startsWith('/rules/')) page = <RuleForm id={route.split('/')[2]} />
  else if (route.startsWith('/customers')) page = <Customers id={route.split('/')[2]} />
  else if (route.startsWith('/orders')) page = <Orders id={route.split('/')[2]} />
  else if (route.startsWith('/channels')) page = <Channels id={route.split('/')[2]} sub={route.split('/')[3]} />
  else if (route === '/settings') page = <Settings onLogout={() => setAuthed(false)} />
  else page = <div className="empty">صفحه پیدا نشد</div>

  const badges = { '/comments': stats.comments_unanswered || 0, '/messages': stats.conversations_unread || 0 }
  const isActive = (path) => path === '/' ? route === '/'
    : path === '/content' ? route.startsWith('/content')
    : path === '/rules' ? route.startsWith('/rules') || route.startsWith('/smart') || route === '/ai/products' || route === '/channels/instagram/rules'
    : path === '/messages' ? route.startsWith('/messages')
    : path === '/comments' ? route.startsWith('/comments')
    : false
  return (
    <div className="app">
      <main><Suspense fallback={<div className="empty">در حال بارگذاری…</div>}>{page}</Suspense></main>
      <nav className="nav" aria-label="منوی اصلی">
        {TABS.map(([path, label, icon]) => (
          <a key={path} href={`#${path}`} className={isActive(path) ? 'active' : ''}>
            <span className="navico"><Icon n={icon} /></span>
            {label}
            {badges[path] > 0 && <span className="badge">{badges[path] > 99 ? '+۹۹' : badges[path].toLocaleString('fa-IR')}</span>}
          </a>
        ))}
      </nav>
    </div>
  )
}
