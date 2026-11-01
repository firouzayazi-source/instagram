// لایه‌ی ارتباط با بک‌اند. روی 401 رویداد خروج می‌فرستد.
export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status }
}

async function call(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'same-origin',
  })
  if (res.status === 401) window.dispatchEvent(new Event('auth:lost'))
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(res.status, data.detail || 'خطا')
  return data
}

export const api = {
  get: (p) => call('GET', p),
  post: (p, b) => call('POST', p, b || {}),
  put: (p, b) => call('PUT', p, b),
  del: (p, b) => call('DELETE', p, b),
  // فایل خام در بدنه، نه فرم
  async upload(p, file) {
    const res = await fetch(p, { method: 'POST', body: file, credentials: 'same-origin' })
    if (res.status === 401) window.dispatchEvent(new Event('auth:lost'))
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new ApiError(res.status, data.detail || (res.status === 413 ? 'حجم فایل زیاد است' : 'خطا'))
    return data
  },
}

export const money = (n) => (n ? `${Number(n).toLocaleString('fa-IR')} تومان` : 'استعلام')
export const pct = (a, b) => (b ? `${Math.round((a / b) * 100).toLocaleString('fa-IR')}٪` : '—')
export const usd = (n) => {
  const v = Number(n || 0)
  return `$${v > 0 && v < 0.1 ? v.toFixed(4) : v.toFixed(2)}`
}

export function timeAgo(ts) {
  const s = Math.max(0, Date.now() / 1000 - ts)
  if (s < 60) return 'همین الان'
  if (s < 3600) return `${fa(Math.floor(s / 60))} دقیقه پیش`
  if (s < 86400) return `${fa(Math.floor(s / 3600))} ساعت پیش`
  if (s < 7 * 86400) return `${fa(Math.floor(s / 86400))} روز پیش`
  return new Date(ts * 1000).toLocaleDateString('fa-IR')
}

export const fa = (n) => Number(n || 0).toLocaleString('fa-IR')
