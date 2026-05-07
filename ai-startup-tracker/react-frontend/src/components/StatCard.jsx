const YALE = '#00356B'

export default function StatCard({ label, value, sub }) {
  return (
    <div style={{
      background: '#fff',
      border: '1px solid #e5e7eb',
      borderLeft: `3px solid ${YALE}`,
      borderRadius: 10,
      padding: '20px 24px',
      flex: 1,
      minWidth: 160,
    }}>
      <div style={{ fontSize: 12, color: '#6b7280', fontWeight: 500, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {label}
      </div>
      <div style={{ fontSize: 28, fontWeight: 600, color: '#111827', lineHeight: 1 }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 4 }}>{sub}</div>
      )}
    </div>
  )
}
