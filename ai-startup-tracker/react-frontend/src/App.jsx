import { useState } from 'react'
import Nav from './components/Nav'
import Dashboard from './components/Dashboard'
import Browse from './components/Browse'

export default function App() {
  const [view, setView] = useState('dashboard')

  return (
    <div style={{ minHeight: '100vh', background: '#f9fafb' }}>
      <Nav view={view} setView={setView} />
      <main style={{ maxWidth: 1200, margin: '0 auto', padding: '32px 24px' }}>
        {view === 'dashboard' ? <Dashboard /> : <Browse />}
      </main>
    </div>
  )
}
