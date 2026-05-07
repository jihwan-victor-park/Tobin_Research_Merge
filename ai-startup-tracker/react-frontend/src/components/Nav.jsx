const YALE = '#00356B'

export default function Nav({ view, setView }) {
  return (
    <nav style={{
      background: '#fff',
      borderBottom: `3px solid ${YALE}`,
      padding: '0 24px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      height: 56,
    }}>
      <span style={{ fontWeight: 600, fontSize: 15, letterSpacing: '-0.01em', color: '#111827' }}>
        Tracking the AI Startup Ecosystem
      </span>
      <div style={{ display: 'flex', gap: 4 }}>
        {['dashboard', 'browse'].map(v => (
          <button
            key={v}
            onClick={() => setView(v)}
            style={{
              padding: '6px 14px',
              borderRadius: 6,
              border: 'none',
              background: view === v ? '#e8eef6' : 'transparent',
              color: view === v ? YALE : '#6b7280',
              fontWeight: view === v ? 600 : 400,
              fontSize: 14,
              textTransform: 'capitalize',
              transition: 'all 0.15s',
            }}
          >
            {v}
          </button>
        ))}
      </div>
    </nav>
  )
}
