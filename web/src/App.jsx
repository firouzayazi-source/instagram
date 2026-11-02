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

const ICONS = {
  home: 'M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z',
  comments: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z',
  messages: 'M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zm0 2l8 6 8-6',
  ai: 'M12 3l1.8 4.7L18.5 9.5 13.8 11.3 12 16l-1.8-4.7L5.5 9.5l4.7-1.8zM19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9zM5 15l.6 1.4L7 17l-1.4.6L5 19l-.6-1.4L3 17l1.4-.6z',
  channels: 'M5 12a7 7 0 0 1 14 0M8.5 12a3.5 3.5 0 0 1 7 0M12 12v8M3 20h18',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm7.4-3a7.4 7.4 0 0 0-.1-1l2-1.6-2-3.4-2.4 1a7.5 7.5 0 0 0-1.7-1L14.8 3H9.2l-.4 2.6a7.5 7.5 0 0 0-1.7 1l-2.4-1-2 3.4 2 1.6a7.4 7.4 0 0 0 0 2l-2 1.6 2 3.4 2.4-1c.5.4 1.1.7 1.7 1l.4 2.6h5.6l.4-2.6c.6-.3 1.2-.6 1.7-1l2.4 1 2-3.4-2-1.6c.1-.3.1-.7.1-1z',
}

function Icon({ d }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>
}

const TABS = [
  ['/', 'پیشخوان', 'home'],
  ['/comments', 'صندوق', 'messages'],
  ['/ai', 'مغز مرکزی', 'ai'],
  ['/channels', 'کانال‌ها', 'channels'],
  ['/settings', 'تنظیمات', 'settings'],
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
  else if (route === '/rules' || route === '/ai/rules') page = <Channels id="instagram" sub="rules" />
  else if (route === '/ai/blocked') page = <Channels id="instagram" sub="blocked" />
  else if (route.startsWith('/ai')) page = <Ai sub={route.split('/')[2]} badges={{ handoffs: stats.ai?.handoffs_open }} />
  else if (route.startsWith('/rules/')) page = <RuleForm id={route.split('/')[2]} />
  else if (route.startsWith('/customers')) page = <Customers id={route.split('/')[2]} />
  else if (route.startsWith('/channels')) page = <Channels id={route.split('/')[2]} sub={route.split('/')[3]} />
  else if (route === '/settings') page = <Settings onLogout={() => setAuthed(false)} />
  else page = <div className="empty">صفحه پیدا نشد</div>

  const badges = { '/comments': (stats.comments_unanswered || 0) + (stats.conversations_unread || 0), '/ai': stats.ai?.handoffs_open }
  return (
    <div className="app">
      <main>{page}</main>
      <nav className="nav" aria-label="منوی اصلی">
        {TABS.map(([path, label, icon]) => {
          const active = path === '/' ? route === '/'
            : path === '/comments' ? route.startsWith('/comments') || route.startsWith('/messages') || route.startsWith('/customers')
            : path === '/channels' ? route.startsWith('/channels') || route.startsWith('/rules')
            : route.startsWith(path)
          return (
            <a key={path} href={`#${path}`} className={active ? 'active' : ''}>
              <Icon d={ICONS[icon]} />
              {label}
              {badges[path] > 0 && <span className="badge">{badges[path] > 99 ? '+۹۹' : badges[path].toLocaleString('fa-IR')}</span>}
            </a>
          )
        })}
      </nav>
    </div>
  )
}
