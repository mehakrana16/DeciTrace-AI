import { useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import { dateTimeStr, money } from '../lib/format'
import DecisionCard from '../components/DecisionCard'
import { Card, EmptyState, ErrorState, LoadingState, PriorityChip, StatusChip } from '../components/ui'

export default function Decisions() {
  const [rows, setRows] = useState<any[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [detail, setDetail] = useState<Record<string, any>>({})
  const [priority, setPriority] = useState('')
  const [status, setStatus] = useState('')
  const [q, setQ] = useState('')

  function load() {
    setLoading(true)
    setError(null)
    const params = new URLSearchParams()
    if (priority) params.set('priority', priority)
    if (status) params.set('status', status)
    api
      .decisions(params.toString() ? `?${params.toString()}` : '')
      .then(setRows)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(load, [priority, status])

  async function toggle(decisionId: string) {
    if (expanded === decisionId) {
      setExpanded(null)
      return
    }
    setExpanded(decisionId)
    if (!detail[decisionId]) {
      try {
        const full = await api.decision(decisionId)
        setDetail((d) => ({ ...d, [decisionId]: full }))
      } catch (e: any) {
        setError(e.message)
      }
    }
  }

  const filtered = useMemo(() => {
    if (!rows) return null
    if (!q.trim()) return rows
    const needle = q.trim().toLowerCase()
    return rows.filter((r) => `${r.customer_name} ${r.customer_id} ${r.decision_id} ${r.decision_text}`.toLowerCase().includes(needle))
  }, [rows, q])

  const counts = useMemo(() => {
    if (!rows) return { HIGH: 0, MEDIUM: 0, LOW: 0, pending: 0, approved: 0, rejected: 0 }
    return {
      HIGH: rows.filter((r) => r.priority === 'HIGH').length,
      MEDIUM: rows.filter((r) => r.priority === 'MEDIUM').length,
      LOW: rows.filter((r) => r.priority === 'LOW').length,
      pending: rows.filter((r) => r.status === 'pending').length,
      approved: rows.filter((r) => r.status === 'approved').length,
      rejected: rows.filter((r) => r.status === 'rejected').length,
    }
  }, [rows])

  if (error) return <ErrorState message={error} onRetry={load} />
  if (loading || !filtered) return <LoadingState label="Loading decisions" rows={4} />

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold tracking-tight text-ink-900">Decisions</h1>
          <p className="mt-1 text-xs text-ink-500">
            {filtered.length} decisions · {counts.HIGH} high · {counts.MEDIUM} medium · {counts.LOW} low ·
            <strong className="text-ink-700"> {counts.pending} awaiting human approval</strong>
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {([
            ['', 'All'],
            ['HIGH', `High ${counts.HIGH}`],
            ['MEDIUM', `Medium ${counts.MEDIUM}`],
            ['LOW', `Low ${counts.LOW}`],
          ] as const).map(([value, label]) => (
            <button
              key={value || 'all'}
              onClick={() => setPriority(value)}
              className={`rounded-md px-2.5 py-1.5 text-xs font-semibold ${priority === value ? 'bg-ink-900 text-white' : 'border border-ink-200 bg-white text-ink-600 hover:bg-ink-50'}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <Card title="Review queue" subtitle="Every AI recommendation requires an explicit human decision before it counts" className="!p-0">
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="block">
            <span className="kv-label">Search</span>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Customer, decision id, text…"
              className="mt-1 w-full rounded-md border border-ink-200 px-3 py-2 text-sm outline-none focus:border-ink-400"
            />
          </label>
          <label className="block">
            <span className="kv-label">Human decision state</span>
            <select value={status} onChange={(e) => setStatus(e.target.value)} className="mt-1 w-full rounded-md border border-ink-200 bg-white px-3 py-2 text-sm outline-none focus:border-ink-400">
              <option value="">All states</option>
              <option value="pending">Pending ({counts.pending})</option>
              <option value="approved">Approved ({counts.approved})</option>
              <option value="rejected">Rejected ({counts.rejected})</option>
            </select>
          </label>
          <div className="flex items-end">
            <div className="w-full rounded-md border border-ink-200 bg-ink-50/60 px-3 py-2">
              <div className="kv-label">Approval status</div>
              <div className="mt-0.5 text-xs text-ink-700">
                {counts.approved} approved · {counts.rejected} rejected · {counts.pending} pending
              </div>
            </div>
          </div>
        </div>
      </Card>

      {filtered.length === 0 ? (
        <EmptyState
          title="No decisions match these filters"
          hint="Clear the search box or set the human decision state back to All states."
        />
      ) : (
        <div className="space-y-3">
          {filtered.map((row) => {
            const isOpen = expanded === row.decision_id
            const full = detail[row.decision_id]
            return (
              <div key={row.decision_id} className="space-y-3">
                <button
                  onClick={() => toggle(row.decision_id)}
                  className="card flex w-full flex-wrap items-center gap-3 px-4 py-3 text-left hover:bg-ink-50"
                >
                  <PriorityChip priority={row.priority} score={row.priority_score} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-bold tracking-tight text-ink-900">{row.customer_name}</span>
                      <span className="mono text-ink-400">{row.customer_id}</span>
                    </div>
                    <p className="mt-0.5 truncate text-xs text-ink-600">{row.decision_text}</p>
                  </div>
                  <div className="hidden shrink-0 text-right lg:block">
                    <div className="mono text-[11px] text-ink-500">{row.decision_id}</div>
                    <div className="text-[10px] text-ink-400">{dateTimeStr(row.generated_at)}</div>
                  </div>
                  <StatusChip status={row.status} />
                  <span className="text-xs font-semibold text-ink-500">{isOpen ? 'Close' : 'Review →'}</span>
                </button>

                {isOpen && (
                  full
                    ? <DecisionCard decision={full} defaultOpen />
                    : <LoadingState label={`Loading ${row.decision_id}`} rows={1} />
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
