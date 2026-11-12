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
