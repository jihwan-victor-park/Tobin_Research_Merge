import { useEffect, useState, useCallback } from 'react'
import CompanyTable from './CompanyTable'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const ACCENT = '#00356B'
const PAGE_SIZE = 50

function useDebounce(value, delay) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

export default function Browse() {
  const [sources, setSources] = useState([])
  const [search, setSearch] = useState('')
  const [source, setSource] = useState('')
  const [aiOnly, setAiOnly] = useState(false)
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const debouncedSearch = useDebounce(search, 300)

  // Load source list from stats
  useEffect(() => {
    fetch(`${API}/api/stats`)
      .then(r => r.json())
      .then(d => setSources(d.sources.map(s => s.source)))
      .catch(() => {})
  }, [])

  // Reset to page 1 when filters change
  useEffect(() => { setPage(1) }, [debouncedSearch, source, aiOnly])

  // Fetch companies
  useEffect(() => {
    setLoading(true)
    setError(null)
    const params = new URLSearchParams({
      page,
      page_size: PAGE_SIZE,
      ...(debouncedSearch && { search: debouncedSearch }),
      ...(source && { source }),
      ...(aiOnly && { ai_only: 'true' }),
    })
    fetch(`${API}/api/companies?${params}`)
      .then(r => { if (!r.ok) throw new Error(r.statusText); return r.json() })
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [debouncedSearch, source, aiOnly, page])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Filters */}
      <div style={{
        background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10,
        padding: '16px 20px', display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap',
      }}>
        <input
          type="text"
          placeholder="Search name or description…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            flex: '1 1 240px', padding: '8px 12px', borderRadius: 6,
            border: '1px solid #d1d5db', fontSize: 14, outline: 'none',
            color: '#111827',
          }}
          onFocus={e => e.target.style.borderColor = ACCENT}
          onBlur={e => e.target.style.borderColor = '#d1d5db'}
        />
        <select
          value={source}
          onChange={e => setSource(e.target.value)}
          style={{
            padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db',
            fontSize: 14, color: source ? '#111827' : '#6b7280', background: '#fff',
            outline: 'none',
          }}
        >
          <option value="">All sources</option>
          {sources.map(s => (
            <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
          ))}
        </select>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', userSelect: 'none' }}>
          <input
            type="checkbox"
            checked={aiOnly}
            onChange={e => setAiOnly(e.target.checked)}
            style={{ accentColor: ACCENT, width: 15, height: 15 }}
          />
          <span style={{ fontSize: 14, color: '#374151' }}>AI only</span>
        </label>
      </div>

      {/* Results summary */}
      {data && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ color: '#6b7280', fontSize: 13 }}>
            {data.total.toLocaleString()} {data.total === 1 ? 'company' : 'companies'}
          </span>
          <span style={{ color: '#9ca3af', fontSize: 12 }}>
            Page {data.page} of {data.pages}
          </span>
        </div>
      )}

      {error && <p style={{ color: '#dc2626' }}>Error: {error}</p>}

      <CompanyTable companies={data?.companies ?? []} loading={loading} />

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
          <PaginationButton onClick={() => setPage(1)} disabled={page === 1}>«</PaginationButton>
          <PaginationButton onClick={() => setPage(p => p - 1)} disabled={page === 1}>‹</PaginationButton>
          <span style={{ padding: '6px 14px', fontSize: 13, color: '#374151' }}>
            {page} / {data.pages}
          </span>
          <PaginationButton onClick={() => setPage(p => p + 1)} disabled={page === data.pages}>›</PaginationButton>
          <PaginationButton onClick={() => setPage(data.pages)} disabled={page === data.pages}>»</PaginationButton>
        </div>
      )}
    </div>
  )
}

function PaginationButton({ onClick, disabled, children }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: '6px 12px', borderRadius: 6,
        border: '1px solid #e5e7eb', background: disabled ? '#f9fafb' : '#fff',
        color: disabled ? '#d1d5db' : '#374151', fontSize: 14,
        cursor: disabled ? 'default' : 'pointer',
      }}
    >
      {children}
    </button>
  )
}
