import React from 'react'
import Icon from '../icons.jsx'
import Schedule from './Schedule.jsx'
import Ideas from './Ideas.jsx'
import Insights from './Insights.jsx'
import { Media } from './Channels.jsx'

const TABS = [['schedule', 'انتشار', 'cal'], ['ideas', 'ایده‌ی محتوا', 'sparkle'], ['insights', 'تحلیل', 'chart'], ['posts', 'پست‌ها', 'grid']]

// محتوا: هر چه به پست، ریلز و استوری مربوط است، یک‌جا
export default function Content({ sub }) {
  const cur = TABS.find(([k]) => k === sub) ? sub : 'schedule'
  return (
    <>
      <header className="topbar">
        <div className="title"><h1>محتوا</h1><span className="sub">انتشار، ایده، تحلیل و پست‌ها</span></div>
        <a href="#/more" className="iconbtn" aria-label="بیشتر"><Icon n="gear" /></a>
      </header>
      <div className="chips" style={{ marginTop: 4 }}>
        {TABS.map(([k, l, ic]) => (
          <a key={k} href={`#/content/${k}`} className={`chip ${cur === k ? 'active' : ''}`} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 16, height: 16, display: 'inline-flex' }}><Icon n={ic} /></span>{l}
          </a>
        ))}
      </div>
      {cur === 'schedule' && <Schedule />}
      {cur === 'ideas' && <Ideas />}
      {cur === 'insights' && <Insights />}
      {cur === 'posts' && <Media />}
    </>
  )
}
