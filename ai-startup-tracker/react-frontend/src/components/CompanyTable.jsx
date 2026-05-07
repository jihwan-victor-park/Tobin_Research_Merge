import { useState } from 'react'

const ACCENT = '#00356B'

function AiScoreBadge({ score }) {
  if (score == null) return <span style={{ color: '#d1d5db', fontSize: 12 }}>—</span>
  const pct = Math.round(score * 100)
  const color = score >= 0.6 ? ACCENT : score >= 0.3 ? '#f59e0b' : '#d1d5db'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{
        width: 40, height: 4, borderRadius: 2,
        background: '#f3f4f6', overflow: 'hidden',
      }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontSize: 12, color, fontWeight: 500 }}>{pct}</span>
    </div>
  )
}

function SourceTag({ source }) {
  if (!source) return null
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 8px',
      background: '#e8eef6',
      color: ACCENT,
      borderRadius: 4,
      fontSize: 11,
      fontWeight: 500,
    }}>
      {source.replace(/_/g, ' ')}
    </span>
  )
}

function Row({ company }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <>
      <tr
        onClick={() => setExpanded(e => !e)}
        style={{
          borderBottom: '1px solid #f3f4f6',
          cursor: 'pointer',
          transition: 'background 0.1s',
        }}
        onMouseEnter={e => e.currentTarget.style.background = '#f9fafb'}
        onMouseLeave={e => e.currentTarget.style.background = ''}
      >
        <td style={{ padding: '12px 16px', fontWeight: 500, color: '#111827' }}>
          {company.name}
        </td>
        <td style={{ padding: '12px 16px' }}>
          <SourceTag source={company.source} />
        </td>
        <td style={{ padding: '12px 16px' }}>
          <AiScoreBadge score={company.ai_score} />
        </td>
        <td style={{ padding: '12px 16px', color: '#6b7280', fontSize: 13 }}>
          {company.domain
            ? <a href={`https://${company.domain}`} target="_blank" rel="noreferrer"
                onClick={e => e.stopPropagation()}
                style={{ color: ACCENT }}>{company.domain}</a>
            : '—'
          }
        </td>
        <td style={{ padding: '12px 16px', color: '#6b7280', maxWidth: 360 }}>
          {company.description
            ? company.description.slice(0, 100) + (company.description.length > 100 ? '…' : '')
            : <span style={{ color: '#d1d5db' }}>—</span>
          }
        </td>
      </tr>
      {expanded && (
        <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
          <td colSpan={5} style={{ padding: '12px 16px 16px 32px' }}>
            <p style={{ color: '#374151', lineHeight: 1.6, marginBottom: company.domain ? 8 : 0 }}>
              {company.description || <em style={{ color: '#9ca3af' }}>No description available.</em>}
            </p>
            {company.domain && (
              <a
                href={`https://${company.domain}`}
                target="_blank"
                rel="noreferrer"
                style={{ color: ACCENT, fontSize: 13 }}
              >
                {company.domain} →
              </a>
            )}
            {company.founded_year && (
              <span style={{ color: '#9ca3af', fontSize: 12, marginLeft: 16 }}>
                Founded {company.founded_year}
              </span>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

export default function CompanyTable({ companies, loading }) {
  if (loading) {
    return <p style={{ color: '#9ca3af', padding: '24px 0' }}>Loading…</p>
  }
  if (!companies.length) {
    return <p style={{ color: '#9ca3af', padding: '24px 0' }}>No results found.</p>
  }

  return (
    <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, overflow: 'hidden' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
            {['Name', 'Source', 'AI Score', 'Domain', 'Description'].map(h => (
              <th key={h} style={{
                padding: '10px 16px', textAlign: 'left',
                fontSize: 12, fontWeight: 600, color: '#6b7280',
                textTransform: 'uppercase', letterSpacing: '0.04em',
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {companies.map(c => <Row key={c.id} company={c} />)}
        </tbody>
      </table>
    </div>
  )
}
