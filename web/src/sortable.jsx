import React, { useRef, useState } from 'react'

// فهرست با جابه‌جایی کشیدنی (موس و لمس): دستگیره را بگیرید و بالا و پایین ببرید.
// renderItem(item, index, handle) — handle همان دستگیره است که هر جای ردیف گذاشته می‌شود.
export default function Sortable({ items, onChange, renderItem, keyOf = (_, i) => i }) {
  const refs = useRef([])
  const [drag, setDrag] = useState(null)        // {from, to, dy, startY}
  const [settling, setSettling] = useState(false)

  function start(e, i) {
    if (items.length < 2) return
    e.preventDefault()
    e.currentTarget.setPointerCapture?.(e.pointerId)
    setDrag({ from: i, to: i, dy: 0, startY: e.clientY })
  }
  function move(e) {
    if (!drag) return
    const y = e.clientY
    let to = drag.from
    refs.current.forEach((el, j) => {
      if (!el || j === drag.from) return
      const r = el.getBoundingClientRect()
      const mid = r.top + r.height / 2
      if (j < drag.from && y < mid) to = Math.min(to, j)
      if (j > drag.from && y > mid) to = Math.max(to, j)
    })
    setDrag({ ...drag, to, dy: y - drag.startY })
  }
  function end() {
    if (!drag) return
    // بعد از رها کردن، دو فریم بی انیمیشن تا ردیف‌ها از جای جدیدشان سُر نخورند
    setSettling(true); requestAnimationFrame(() => requestAnimationFrame(() => setSettling(false)))
    if (drag.to !== drag.from) {
      const l = [...items]
      const [x] = l.splice(drag.from, 1)
      l.splice(drag.to, 0, x)
      onChange(l)
    }
    setDrag(null)
  }

  return (
    <div className="sortable">
      {items.map((it, i) => {
        const h = refs.current[drag?.from]?.offsetHeight || 0
        let shift = 0
        if (drag && i !== drag.from) {
          if (drag.from < i && i <= drag.to) shift = -h - 8
          if (drag.to <= i && i < drag.from) shift = h + 8
        }
        const dragging = drag?.from === i
        const handle = (
          <span className="drag-h" role="button" aria-label="جابه‌جایی (بکشید)" title="بکشید"
            onPointerDown={(e) => start(e, i)} onPointerMove={move} onPointerUp={end} onPointerCancel={end}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><circle cx="9" cy="6" r="1.6" /><circle cx="15" cy="6" r="1.6" /><circle cx="9" cy="12" r="1.6" /><circle cx="15" cy="12" r="1.6" /><circle cx="9" cy="18" r="1.6" /><circle cx="15" cy="18" r="1.6" /></svg>
          </span>
        )
        return (
          <div key={keyOf(it, i)} ref={(el) => { refs.current[i] = el }} className={dragging ? 'sort-item dragging' : 'sort-item'}
            style={{ transform: `translateY(${dragging ? drag.dy : shift}px)`, transition: dragging || settling ? 'none' : 'transform .15s' }}>
            {renderItem(it, i, items.length > 1 ? handle : null)}
          </div>
        )
      })}
    </div>
  )
}

// کادر متنی که با نوشتن بلند می‌شود (از یک خط شروع می‌کند)
export function AutoText({ value, onChange, ...rest }) {
  const ref = useRef(null)
  const fit = (el) => { if (el) { el.style.height = 'auto'; el.style.height = `${el.scrollHeight + 2}px` } }
  return <textarea ref={(el) => { ref.current = el; fit(el) }} rows={1} value={value} onChange={(e) => { fit(e.target); onChange(e) }} {...rest} />
}
