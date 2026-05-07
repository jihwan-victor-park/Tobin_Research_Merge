import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'

const YALE = '#00356B'
const YALE_MID = '#4A7AAF'

const fmt = (v) => v.toLocaleString()

function CustomTooltip({ active, payload, label, aiPct }) {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  return (
    <div style={{
      background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8,
      padding: '10px 14px', fontSize: 13,
    }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{label}</div>
      <div>Total: {fmt(d?.total ?? 0)}</div>
      {!aiPct && <div>AI-flagged: {fmt(d?.ai_flagged ?? 0)}</div>}
      {aiPct && <div>AI %: {d?.ai_pct ?? 0}%</div>}
    </div>
  )
}

export function TotalBySourceChart({ data }) {
  return (
    <div style={{
      background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10,
      padding: '20px 24px',
    }}>
      <div style={{ fontWeight: 600, marginBottom: 16, fontSize: 14 }}>Companies by Source</div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 0, right: 0, bottom: 48, left: 0 }}>
          <XAxis
            dataKey="source"
            tick={{ fontSize: 11, fill: '#6b7280' }}
            angle={-40}
            textAnchor="end"
            interval={0}
          />
          <YAxis tick={{ fontSize: 11, fill: '#6b7280' }} width={45} tickFormatter={fmt} />
          <Tooltip content={<CustomTooltip />} />
          <Bar dataKey="total" radius={[3, 3, 0, 0]}>
            {data.map((_, i) => <Cell key={i} fill={YALE} fillOpacity={0.85} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function AIPctBySourceChart({ data }) {
  const sorted = [...data].sort((a, b) => b.ai_pct - a.ai_pct)
  return (
    <div style={{
      background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10,
      padding: '20px 24px',
    }}>
      <div style={{ fontWeight: 600, marginBottom: 16, fontSize: 14 }}>AI-Flagged % by Source</div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={sorted} margin={{ top: 0, right: 0, bottom: 48, left: 0 }}>
          <XAxis
            dataKey="source"
            tick={{ fontSize: 11, fill: '#6b7280' }}
            angle={-40}
            textAnchor="end"
            interval={0}
          />
          <YAxis tick={{ fontSize: 11, fill: '#6b7280' }} width={38} tickFormatter={v => `${v}%`} />
          <Tooltip content={<CustomTooltip aiPct />} />
          <Bar dataKey="ai_pct" radius={[3, 3, 0, 0]}>
            {sorted.map((_, i) => <Cell key={i} fill={YALE_MID} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
