import { useEffect, useState } from 'react'
import StatCard from './StatCard'
import { TotalBySourceChart, AIPctBySourceChart } from './SourceChart'
import FoundingYearChart from './FoundingYearChart'
import ScoreDistChart from './ScoreDistChart'
import GlobeView from './GlobeView'
import Scout from './Scout'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch(`${API}/api/stats`)
      .then(r => { if (!r.ok) throw new Error(r.statusText); return r.json() })
      .then(setStats)
      .catch(e => setError(e.message))
  }, [])

  if (error) return <p style={{ color: '#dc2626' }}>Failed to load stats: {error}</p>
  if (!stats) return <p style={{ color: '#9ca3af' }}>Loading…</p>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Row 1: Hero stat cards */}
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <StatCard label="Total Companies" value={stats.total_companies.toLocaleString()} />
        <StatCard label="AI-Flagged" value={stats.ai_flagged.toLocaleString()} sub="ai_score ≥ 0.6" />
        <StatCard label="AI Percentage" value={`${stats.ai_pct}%`} />
        <StatCard label="Have Domain" value={stats.with_domain.toLocaleString()} />
      </div>

      {/* Row 2: Source charts */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <TotalBySourceChart data={stats.sources} />
        <AIPctBySourceChart data={stats.sources} />
      </div>

      {/* Row 3: Founding year + score distribution */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <FoundingYearChart />
        <ScoreDistChart />
      </div>

      {/* Row 4: Globe — full width */}
      <GlobeView />

      {/* Row 5: Scout agent */}
      <Scout />
    </div>
  )
}
