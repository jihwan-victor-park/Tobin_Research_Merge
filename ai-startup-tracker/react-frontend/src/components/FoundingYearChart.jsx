import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const ACCENT = '#00356B'

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8,
      padding: '10px 14px', fontSize: 13,
    }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{label}</div>
      <div>Companies: {payload[0]?.value?.toLocaleString()}</div>
    </div>
  )
}

export default function FoundingYearChart() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch(`${API}/api/stats/founding-years`)
      .then(r => { if (!r.ok) throw new Error(r.statusText); return r.json() })
      .then(raw => {
        const known = raw.filter(d => d.year !== null)
        const unknown = raw.find(d => d.year === null)
        const result = known.map(d => ({ label: String(d.year), count: d.count }))
        if (unknown) result.push({ label: 'Unknown', count: unknown.count })
        setData(result)
      })
      .catch(e => setError(e.message))
  }, [])

  return (
    <div style={{
      background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10,
      padding: '20px 24px',
    }}>
      <div style={{ fontWeight: 600, marginBottom: 16, fontSize: 14 }}>Companies Founded per Year</div>
      {error && <p style={{ color: '#dc2626', fontSize: 13 }}>Failed to load: {error}</p>}
      {!data && !error && <p style={{ color: '#9ca3af', fontSize: 13 }}>Loading…</p>}
      {data && (
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={data} margin={{ top: 0, right: 0, bottom: 40, left: 0 }}>
            <XAxis
              dataKey="label"
              tick={{ fontSize: 10, fill: '#6b7280' }}
              angle={-45}
              textAnchor="end"
              interval={0}
            />
            <YAxis tick={{ fontSize: 11, fill: '#6b7280' }} width={40} />
            <Tooltip content={<CustomTooltip />} />
            <Bar dataKey="count" radius={[3, 3, 0, 0]}>
              {data.map((d, i) => (
                <Cell
                  key={i}
                  fill={d.label === 'Unknown' ? '#d1d5db' : ACCENT}
                  fillOpacity={d.label === 'Unknown' ? 0.6 : 0.85}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
