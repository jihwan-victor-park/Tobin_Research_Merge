import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const ACCENT = '#00356B'
const THRESHOLD = 0.6 // ai_score cutoff for "AI-flagged"

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const flagged = parseFloat(label) >= THRESHOLD
  return (
    <div style={{
      background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8,
      padding: '10px 14px', fontSize: 13,
    }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>Score {label}</div>
      <div>Companies: {payload[0]?.value?.toLocaleString()}</div>
      {flagged && <div style={{ color: ACCENT, fontSize: 12 }}>AI-flagged range</div>}
    </div>
  )
}

export default function ScoreDistChart() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch(`${API}/api/stats/score-distribution`)
      .then(r => { if (!r.ok) throw new Error(r.statusText); return r.json() })
      .then(setData)
      .catch(e => setError(e.message))
  }, [])

  return (
    <div style={{
      background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10,
      padding: '20px 24px',
    }}>
      <div style={{ fontWeight: 600, marginBottom: 4, fontSize: 14 }}>AI Score Distribution</div>
      <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 16 }}>
        Blue bars ≥ 0.6 are AI-flagged
      </div>
      {error && <p style={{ color: '#dc2626', fontSize: 13 }}>Failed to load: {error}</p>}
      {!data && !error && <p style={{ color: '#9ca3af', fontSize: 13 }}>Loading…</p>}
      {data && (
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={data} margin={{ top: 0, right: 0, bottom: 8, left: 0 }}>
            <XAxis
              dataKey="bucket"
              tick={{ fontSize: 10, fill: '#6b7280' }}
              angle={-30}
              textAnchor="end"
              height={48}
            />
            <YAxis tick={{ fontSize: 11, fill: '#6b7280' }} width={50} tickFormatter={v => v.toLocaleString()} />
            <Tooltip content={<CustomTooltip />} />
            <Bar dataKey="count" radius={[3, 3, 0, 0]}>
              {data.map((d, i) => {
                const lo = parseFloat(d.bucket)
                const flagged = lo >= THRESHOLD
                return (
                  <Cell
                    key={i}
                    fill={flagged ? ACCENT : '#93c5fd'}
                    fillOpacity={flagged ? 0.85 : 0.5}
                  />
                )
              })}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
