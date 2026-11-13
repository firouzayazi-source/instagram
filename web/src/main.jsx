import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './styles.css'

createRoot(document.getElementById('root')).render(<App />)

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}))
}

// آیفون در حالت اپ گاهی با دو انگشت زوم می‌کند و منوی پایین از جا درمی‌رود (دو ضربه را CSS می‌بندد)
document.addEventListener('gesturestart', (e) => e.preventDefault())
