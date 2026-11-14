// سرویس‌ورکر: باز شدن سریع پنل و دریافت اعلان پوش
// - فایل‌های /assets/ (نام هش‌دار، هرگز عوض نمی‌شوند): اول از کش، بی‌انتظار شبکه
// - صفحه‌ی اصلی: از شبکه، ولی اگر تا ۲.۵ ثانیه جواب نیامد، نسخه‌ی کش‌شده (اینترنت کند همراه)
const CACHE = 'panel-v2'
const NAV_TIMEOUT = 2500

self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))))
  self.clients.claim()
})

function put(req, res) {
  if (res && res.ok) caches.open(CACHE).then((c) => c.put(req, res.clone()))
  return res
}

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url)
  if (e.request.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api/') || url.pathname.startsWith('/media/')) return
  if (url.pathname.startsWith('/assets/')) {
    e.respondWith(caches.match(e.request).then((hit) => hit || fetch(e.request).then((res) => put(e.request, res))))
    return
  }
  const key = e.request.mode === 'navigate' ? '/' : e.request     // همه‌ی مسیرهای پنل یک صفحه‌اند (SPA)
  const net = fetch(e.request).then((res) => put(key, res))
  e.respondWith(new Promise((resolve) => {
    let done = false
    const fallback = () => caches.match(key).then((hit) => { if (hit && !done) { done = true; resolve(hit) } })
    const t = setTimeout(fallback, NAV_TIMEOUT)
    net.then((res) => { clearTimeout(t); if (!done) { done = true; resolve(res) } })
      .catch(() => { clearTimeout(t); caches.match(key).then((hit) => { if (!done) { done = true; resolve(hit || Response.error()) } }) })
  }))
})
self.addEventListener('push', (e) => {
  let data = {}
  try { data = e.data.json() } catch { data = { title: 'پیام جدید', body: e.data && e.data.text() } }
  e.waitUntil(
    self.registration.showNotification(data.title || 'استوک لند', {
      body: data.body || '',
      icon: '/icon-192.png',
      badge: '/icon-192.png',
      dir: 'rtl',
      lang: 'fa',
      data: { url: data.url || '/' },
    })
  )
})

self.addEventListener('notificationclick', (e) => {
  e.notification.close()
  const url = (e.notification.data && e.notification.data.url) || '/'
  e.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const c of list) if ('focus' in c) { c.navigate(url); return c.focus() }
      return self.clients.openWindow(url)
    })
  )
})
