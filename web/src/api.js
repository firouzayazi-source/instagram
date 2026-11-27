// لایه‌ی ارتباط با بک‌اند. روی 401 رویداد خروج می‌فرستد.
export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status }
}

// خطای بی‌توضیح سرور یا شبکه، به زبان ساده و با کد، تا علت معلوم باشد
function plainError(status) {
  if (status === 502 || status === 503) return `سرور در دسترس نیست (کد ${status})؛ احتمالاً در حال ری‌استارت است. یک دقیقه‌ی دیگر دوباره امتحان کنید.`
  if (status === 504) return 'جواب سرور بیش از حد طول کشید (کد ۵۰۴). دوباره امتحان کنید.'
  if (status === 413) return 'حجم فایل زیاد است'
  return `خطای سرور (کد ${status})`
}

async function call(method, path, body) {
  let res
  try {
    res = await fetch(path, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
      credentials: 'same-origin',
    })
  } catch {
    throw new ApiError(0, 'اتصال به سرور قطع شد؛ اینترنت را بررسی کنید یا چند ثانیه‌ی دیگر دوباره امتحان کنید.')
  }
  if (res.status === 401) window.dispatchEvent(new Event('auth:lost'))
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(res.status, data.detail || plainError(res.status))
  return data
}

// سرعت (۶ آذر ۱۴۰۵): جواب GET چند ثانیه در حافظه می‌ماند تا برگشتن به یک صفحه فوری باشد، و دو درخواست هم‌زمان
// یکسان یکی می‌شوند. هر تغییر (POST/PUT/DELETE) کل حافظه را پاک می‌کند تا هیچ صفحه‌ای داده‌ی کهنه نشان ندهد.
const CACHE_MS = 8000
const cache = new Map()      // مسیر ← { at, data }
const inflight = new Map()   // مسیر ← Promise

function cachedGet(p) {
  const hit = cache.get(p)
  if (hit && Date.now() - hit.at < CACHE_MS) return Promise.resolve(hit.data)
  if (inflight.has(p)) return inflight.get(p)
  const req = call('GET', p).then((data) => { cache.set(p, { at: Date.now(), data }); return data })
    .finally(() => inflight.delete(p))
  inflight.set(p, req)
  return req
}

function mutate(method, p, b) {
  cache.clear()
  return call(method, p, b)
}

export const api = {
  get: cachedGet,
  fresh: (p) => { cache.delete(p); return cachedGet(p) },   // برای دکمه‌ی «تازه‌سازی» و خوانش دوره‌ای
  post: (p, b) => mutate('POST', p, b || {}),
  put: (p, b) => mutate('PUT', p, b),
  del: (p, b) => mutate('DELETE', p, b),
  // فایل خام در بدنه، نه فرم
  async upload(p, file) {
    cache.clear()
    const res = await fetch(p, { method: 'POST', body: file, credentials: 'same-origin' })
    if (res.status === 401) window.dispatchEvent(new Event('auth:lost'))
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new ApiError(res.status, data.detail || plainError(res.status))
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
