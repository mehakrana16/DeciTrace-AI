import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { money, pct, priorityStyle } from '../lib/format'
import { Card, EmptyState, ErrorState, LoadingState, PriorityChip, ScoreBar, StatusChip } from '../components/ui'

const PRIORITIES = ['', 'HIGH', 'MEDIUM', 'LOW']

export default function Customers() {
  const [rows, setRows] = useState<any[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const [priority, setPriority] = useState('')
  const [region, setRegion] = useState('')
  const [sortKey, setSortKey] = useState<'priority' | 'revenue' | 'value' | 'name'>('priority')

  function load() {
    setError(null)
    const params = new URLSearchParams()
    if (priority) params.set('priority', priority)
    if (region) params.set('region', region)
    api
      .customers(params.toString() ? `?${params.toString()}` : '')
      .then(setRows)
      .catch((e) => setError(e.message))
  }

  useEffect(load, [priority, region])

  const regions = useMemo(() => {
    if (!rows) return []
    return Array.from(new Set(rows.map((r) => r.region))).sort()
  }, [rows])

  const filtered = useMemo(() => {
    if (!rows) return null
    let out = rows
    if (q.trim()) {
      const needle = q.trim().toLowerCase()
      out = out.filter((r) =>
        `${r.customer_name} ${r.customer_id} ${r.industry} ${r.region} ${r.segment} ${r.owner}`
          .toLowerCase()
          .includes(needle),
      )
    }
    const order = { HIGH: 0, MEDIUM: 1, LOW: 2 }
    out = [...out].sort((a, b) => {
      if (sortKey === 'priority') return (order[a.priority] ?? 3) - (order[b.priority] ?? 3) || (b.priority_score ?? 0) - (a.priority_score ?? 0)
      if (sortKey === 'revenue') return b.revenue_90d - a.revenue_90d
      if (sortKey === 'value') return b.account_value - a.account_value
      return a.customer_name.localeCompare(b.customer_name)
    })
    return out
  }, [rows, q, sortKey])

  if (error) return <ErrorState message={error} onRetry={load} />
  if (!rows || !filtered) return <LoadingState label="Loading customer book" rows={5} />

  const highCount = filtered.filter((r) => r.priority === 'HIGH').length

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold tracking-tight text-ink-900">Customers</h1>
          <p className="mt-1 text-xs text-ink-500">
            {filtered.length} of {rows.length} accounts · <strong className="text-red-600">{highCount} high priority</strong> · scored by the
            deterministic decision engine
          </p>
        </div>
      </div>

      <Card title="Filters" className="!p-0">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block">
            <span className="kv-label">Search</span>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Name, id, industry, owner…"
              className="mt-1 w-full rounded-md border border-ink-200 px-3 py-2 text-sm outline-none focus:border-ink-400"
            />
          </label>
          <label className="block">
            <span className="kv-label">Priority</span>
            <select
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              className="mt-1 w-full rounded-md border border-ink-200 bg-white px-3 py-2 text-sm outline-none focus:border-ink-400"
            >
              {PRIORITIES.map((p) => (
                <option key={p || 'all'} value={p}>{p || 'All priorities'}</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="kv-label">Region</span>
            <select
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              className="mt-1 w-full rounded-md border border-ink-200 bg-white px-3 py-2 text-sm outline-none focus:border-ink-400"
            >
              <option value="">All regions</option>
              {regions.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="kv-label">Sort by</span>
            <select
              value={sortKey}
              onChange={(e) => setSortKey(e.target.value as any)}
              className="mt-1 w-full rounded-md border border-ink-200 bg-white px-3 py-2 text-sm outline-none focus:border-ink-400"
            >
              <option value="priority">Priority (then score)</option>
              <option value="revenue">90-day revenue</option>
              <option value="value">Contracted value</option>
              <option value="name">Customer name</option>
            </select>
          </label>
        </div>
      </Card>

      {filtered.length === 0 ? (
        <EmptyState
          title="No customers match these filters"
          hint="Try clearing the search box or switching the priority filter back to All priorities."
        />
      ) : (
        <Card title="Account book" subtitle="Click a customer to open the full evidence trace" className="!p-0">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  {['Customer', 'Priority', 'Score', 'Industry / region', 'Revenue 90d', 'Usage Δ', 'Open tickets', 'Status', ''].map((h) => (
                    <th key={h} className="table-head px-3 py-2 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => {
                  const s = priorityStyle(c.priority)
                  return (
                    <tr key={c.customer_id} className="hover:bg-ink-50">
                      <td className="table-cell">
                        <div className="flex items-center gap-2">
                          <span className={`h-6 w-1 rounded-full ${s.bar}`} />
                          <div>
                            <Link to={`/customers/${c.customer_id}`} className="font-semibold text-ink-900 hover:underline">
                              {c.customer_name}
                            </Link>
                            <div className="mono text-ink-400">{c.customer_id} · {c.owner}</div>
                          </div>
                        </div>
                      </td>
                      <td className="table-cell whitespace-nowrap">
                        <PriorityChip priority={c.priority ?? 'LOW'} />
                      </td>
                      <td className="table-cell">
                        <div className="w-24">
                          <div className="font-mono text-xs font-semibold tabular-nums text-ink-800">
                            {(c.priority_score ?? 0).toFixed(1)}
                          </div>
                          <div className="mt-1"><ScoreBar score={c.priority_score ?? 0} priority={c.priority ?? 'LOW'} /></div>
                        </div>
                      </td>
                      <td className="table-cell text-xs text-ink-600">
                        {c.industry}
                        <div className="text-ink-400">{c.region} · {c.segment}</div>
                      </td>
                      <td className="table-cell whitespace-nowrap">
                        <div className="font-mono text-xs font-semibold text-ink-800">{money(c.revenue_90d)}</div>
                        <div className="text-[10px] text-ink-400">value {money(c.account_value)}</div>
                      </td>
                      <td className={`table-cell font-mono text-xs font-semibold ${c.usage_delta_pct === null ? 'text-ink-400' : c.usage_delta_pct < 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                        {pct(c.usage_delta_pct)}
                      </td>
                      <td className="table-cell font-mono text-xs tabular-nums">
                        {c.open_tickets > 0 ? <span className="font-semibold text-red-600">{c.open_tickets}</span> : <span className="text-ink-400">0</span>}
                      </td>
                      <td className="table-cell"><StatusChip status={c.status} /></td>
                      <td className="table-cell text-right">
                        <Link to={`/customers/${c.customer_id}`} className="text-xs font-semibold text-ink-700 hover:underline">
                          Open →
                        </Link>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}
