// بعد از ساخت: نسخه‌ی فشرده‌ی ‎.gz‎ کنار فایل‌های js، css و svg (سرور همان را به مرورگر می‌دهد؛ حجم حدود یک‌چهارم)
import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { gzipSync, constants } from 'node:zlib'

let n = 0, before = 0, after = 0
function walk(dir) {
  for (const f of readdirSync(dir)) {
    const p = join(dir, f)
    if (statSync(p).isDirectory()) { walk(p); continue }
    if (!/\.(js|css|svg|html|webmanifest)$/.test(f)) continue
    const raw = readFileSync(p)
    if (raw.length < 1024) continue
    const gz = gzipSync(raw, { level: constants.Z_BEST_COMPRESSION })
    writeFileSync(p + '.gz', gz)
    n++; before += raw.length; after += gz.length
  }
}
walk(new URL('../dist', import.meta.url).pathname)
console.log(`gzip: ${n} files, ${Math.round(before / 1024)}KB → ${Math.round(after / 1024)}KB`)
