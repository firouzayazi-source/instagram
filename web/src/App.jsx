import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import Login from './pages/Login.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Comments from './pages/Comments.jsx'
import Messages from './pages/Messages.jsx'
import Ai from './pages/Ai.jsx'
import RuleForm from './pages/RuleForm.jsx'
import Settings from './pages/Settings.jsx'
import Channels from './pages/Channels.jsx'
import Customers from './pages/Customers.jsx'
import Orders from './pages/Orders.jsx'
import Rules from './pages/Rules.jsx'
import Content from './pages/Content.jsx'
import More from './pages/More.jsx'
import Icon from './icons.jsx'

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
    : path === '/rules' ? route.startsWith('/rules') || route === '/channels/instagram/rules'
    : path === '/messages' ? route.startsWith('/messages')
    : path === '/comments' ? route.startsWith('/comments')
    : false
  return (
    <div className="app">
      <main>{page}</main>
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
