import { useEffect, useRef, useState } from 'react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const YALE = '#00356B'
const MAX_HISTORY = 10
const POLL_MS = 3000

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }) {
  const styles = {
    pending:  { bg: '#f3f4f6', color: '#6b7280', label: 'Pending' },
    running:  { bg: '#eff6ff', color: YALE,      label: 'Running', pulse: true },
    complete: { bg: '#f0fdf4', color: '#16a34a', label: 'Complete' },
    error:    { bg: '#fef2f2', color: '#dc2626', label: 'Error' },
  }
  const s = styles[status] ?? styles.pending
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '2px 10px', borderRadius: 99, fontSize: 12, fontWeight: 500,
      background: s.bg, color: s.color,
    }}>
      {s.pulse && (
        <span style={{
          display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
          background: YALE, animation: 'pulse 1.4s ease-in-out infinite',
        }} />
      )}
      {s.label}
    </span>
  )
}

// ── Result display ────────────────────────────────────────────────────────────

function ToolCallList({ calls }) {
  const [open, setOpen] = useState(false)
  if (!calls?.length) return null
  return (
    <div style={{ marginTop: 12 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          background: 'none', border: 'none', padding: 0,
          color: '#6b7280', fontSize: 13, cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: 4,
        }}
      >
        <span style={{ fontSize: 11 }}>{open ? '▼' : '▶'}</span>
        {calls.length} tool call{calls.length !== 1 ? 's' : ''} made
      </button>
      {open && (
        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
          {calls.map((c, i) => (
            <div key={i} style={{
              padding: '6px 10px', background: '#f9fafb', borderRadius: 6,
              fontSize: 12, fontFamily: 'monospace', color: '#374151',
              border: '1px solid #e5e7eb',
            }}>
              <span style={{ color: YALE, fontWeight: 600 }}>{c.tool}</span>
              {c.input_summary && (
                <span style={{ color: '#6b7280' }}> — {c.input_summary}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function InstructionDraft({ draft }) {
  const [open, setOpen] = useState(true)
  if (!draft || Object.keys(draft).length === 0) return null
  return (
    <div style={{ marginTop: 12 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          background: 'none', border: 'none', padding: 0,
          color: YALE, fontSize: 13, fontWeight: 600, cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: 4, marginBottom: 6,
        }}
      >
        <span style={{ fontSize: 11 }}>{open ? '▼' : '▶'}</span>
        Instruction draft
      </button>
      {open && (
        <pre style={{
          background: '#f8fafc', border: '1px solid #e5e7eb', borderRadius: 8,
          padding: '12px 14px', fontSize: 12, fontFamily: 'monospace',
          color: '#1e293b', overflowX: 'auto', whiteSpace: 'pre-wrap',
          wordBreak: 'break-word', maxHeight: 320, overflowY: 'auto',
          margin: 0,
        }}>
          {JSON.stringify(draft, null, 2)}
        </pre>
      )}
    </div>
  )
}

function JobResult({ job }) {
  if (job.status === 'error') {
    return (
      <div style={{
        marginTop: 8, padding: '10px 14px', background: '#fef2f2',
        border: '1px solid #fecaca', borderRadius: 8, fontSize: 13, color: '#b91c1c',
      }}>
        {job.error}
      </div>
    )
  }
  if (job.status !== 'complete' || !job.result) return null

  const { summary, tool_calls, instruction_draft } = job.result
  return (
    <div>
      {summary && (
        <div style={{
          marginTop: 8, fontSize: 13, color: '#374151', lineHeight: 1.65,
          whiteSpace: 'pre-wrap',
        }}>
          {summary}
        </div>
      )}
      <InstructionDraft draft={instruction_draft} />
      <ToolCallList calls={tool_calls} />
    </div>
  )
}

// ── History item ──────────────────────────────────────────────────────────────

function HistoryItem({ job, isActive }) {
  const [expanded, setExpanded] = useState(false)
  const short = job.url.replace(/^https?:\/\//, '').split('/')[0]
  const ts = new Date(job.submitted_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

  return (
    <div style={{
      border: '1px solid #e5e7eb', borderRadius: 8,
      background: isActive ? '#f8fbff' : '#fff', overflow: 'hidden',
    }}>
      <div
        onClick={() => setExpanded(e => !e)}
        style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '10px 14px', cursor: 'pointer',
        }}
      >
        <StatusBadge status={job.status} />
        <span style={{ flex: 1, fontSize: 13, color: '#111827', fontWeight: 500 }}
          title={job.url}>{short}</span>
        <span style={{ fontSize: 11, color: '#9ca3af' }}>{ts}</span>
        <span style={{ fontSize: 11, color: '#9ca3af' }}>{expanded ? '▲' : '▼'}</span>
      </div>
      {expanded && (
        <div style={{ padding: '0 14px 12px', borderTop: '1px solid #f3f4f6' }}>
          <div style={{ fontSize: 12, color: '#6b7280', margin: '8px 0 4px' }}>{job.url}</div>
          <JobResult job={job} />
        </div>
      )}
    </div>
  )
}

// ── Main Scout component ──────────────────────────────────────────────────────

export default function Scout() {
  const [url, setUrl] = useState('')
  const [urlError, setUrlError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [activeJob, setActiveJob] = useState(null)   // JobStatus dict
  const [history, setHistory] = useState([])         // array of JobStatus dicts, newest first
  const pollRef = useRef(null)

  // Start polling when activeJob is pending or running
  useEffect(() => {
    if (!activeJob) return
    if (activeJob.status === 'complete' || activeJob.status === 'error') return

    pollRef.current = setInterval(async () => {
      try {
        const r = await fetch(`${API}/api/scout/${activeJob.job_id}`)
        const updated = await r.json()
        setActiveJob(updated)
        setHistory(prev =>
          prev.map(j => j.job_id === updated.job_id ? updated : j)
        )
        if (updated.status === 'complete' || updated.status === 'error') {
          clearInterval(pollRef.current)
        }
      } catch {
        // network blip — keep polling
      }
    }, POLL_MS)

    return () => clearInterval(pollRef.current)
  }, [activeJob?.job_id, activeJob?.status])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setUrlError('')
    if (!url.startsWith('http')) {
      setUrlError('URL must start with http or https')
      return
    }
    setSubmitting(true)
    try {
      const r = await fetch(`${API}/api/scout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      })
      if (!r.ok) throw new Error(await r.text())
      const { job_id } = await r.json()

      // Immediately fetch initial status
      const statusR = await fetch(`${API}/api/scout/${job_id}`)
      const job = await statusR.json()

      setActiveJob(job)
      setHistory(prev => [job, ...prev].slice(0, MAX_HISTORY))
      setUrl('')
    } catch (err) {
      setUrlError(`Submit failed: ${err.message}`)
    } finally {
      setSubmitting(false)
    }
  }

  const isRunning = activeJob?.status === 'pending' || activeJob?.status === 'running'

  return (
    <div id="scout-section" style={{
      background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10,
      padding: '24px 28px',
    }}>
      {/* Pulse animation */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.4; transform: scale(0.85); }
        }
      `}</style>

      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontWeight: 600, fontSize: 15, color: '#111827' }}>Scout Agent</div>
        <div style={{ fontSize: 13, color: '#6b7280', marginTop: 3 }}>
          Investigate a new source — the agent will analyze the URL and draft a scraping instruction
        </div>
      </div>

      {/* Submit form */}
      <form onSubmit={handleSubmit} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 20 }}>
        <div style={{ flex: 1 }}>
          <input
            type="text"
            value={url}
            onChange={e => { setUrl(e.target.value); setUrlError('') }}
            placeholder="https://accelerator.com/portfolio"
            style={{
              width: '100%', padding: '9px 13px', borderRadius: 7,
              border: `1px solid ${urlError ? '#fca5a5' : '#d1d5db'}`,
              fontSize: 14, color: '#111827', outline: 'none',
              background: '#fff',
            }}
            onFocus={e => e.target.style.borderColor = YALE}
            onBlur={e => e.target.style.borderColor = urlError ? '#fca5a5' : '#d1d5db'}
            disabled={submitting || isRunning}
          />
          {urlError && (
            <div style={{ fontSize: 12, color: '#dc2626', marginTop: 4 }}>{urlError}</div>
          )}
        </div>
        <button
          type="submit"
          disabled={submitting || isRunning || !url}
          style={{
            padding: '9px 20px', borderRadius: 7, border: 'none',
            background: submitting || isRunning || !url ? '#e5e7eb' : YALE,
            color: submitting || isRunning || !url ? '#9ca3af' : '#fff',
            fontWeight: 600, fontSize: 14, cursor: submitting || isRunning || !url ? 'not-allowed' : 'pointer',
            whiteSpace: 'nowrap', transition: 'background 0.15s',
          }}
        >
          {submitting ? 'Submitting…' : isRunning ? 'Running…' : 'Run Scout'}
        </button>
      </form>

      {/* Active job status */}
      {activeJob && (
        <div style={{
          border: `1px solid ${activeJob.status === 'error' ? '#fecaca' : activeJob.status === 'complete' ? '#bbf7d0' : '#e5e7eb'}`,
          borderRadius: 10, padding: '16px 18px', marginBottom: 20,
          background: activeJob.status === 'running' ? '#f8fbff' : '#fff',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <StatusBadge status={activeJob.status} />
            <span style={{ fontSize: 13, color: '#374151', flex: 1 }}>{activeJob.url}</span>
          </div>
          {(activeJob.status === 'pending' || activeJob.status === 'running') && (
            <div style={{ fontSize: 13, color: '#6b7280' }}>
              Agent is investigating the URL — polling every 3s…
            </div>
          )}
          <JobResult job={activeJob} />
        </div>
      )}

      {/* Job history */}
      {history.length > 0 && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 10 }}>
            Session history
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {history.map(job => (
              <HistoryItem
                key={job.job_id}
                job={job}
                isActive={job.job_id === activeJob?.job_id}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
