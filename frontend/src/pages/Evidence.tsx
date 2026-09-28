import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { dateStr, relativeDays } from '../lib/format'
import { BarList, Card, EmptyState, ErrorState, LoadingState, PriorityChip } from '../components/ui'

const SOURCE_STYLES: Record<string, string> = {
  business_notes: 'border-sky-300 bg-sky-50 text-sky-800',
  support_tickets: 'border-red-300 bg-red-50 text-red-700',
  sales: 'border-emerald-300 bg-emerald-50 text-emerald-800',
  usage_records: 'border-violet-300 bg-violet-50 text-violet-800',
}

export default function Evidence() {
  const [decisions, setDecisions] = useState<any[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [items, setItems] = useState<any[] | null>(null)
  const [filter, setFilter] = useState('')

  useEffect(() => {
    api
      .decisions('?limit=200')
      .then((rows) => {
        setDecisions(rows)
        if (rows.length) setSelected(rows[0].decision_id)
      })
      .catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    if (!selected) return
    setItems(null)
    api.evidence(selected).then(setItems).catch((e) => setError(e.message))
  }, [selected])

  const breakdown = useMemo(() => {
    if (!items) return []
    const counts: Record<string, number> = {}
    items.forEach((i) => {
      counts[i.source_table] = (counts[i.source_table] ?? 0) + 1
    })
    return Object.entries(counts).map(([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value)
  }, [items])

  const filtered = useMemo(() => {
    if (!items) return null
    if (!filter) return items
    return items.filter((i) => i.source_table === filter)
  }, [items, filter])

  if (error) return <ErrorState message={error} />
  if (!decisions) return <LoadingState label="Loading evidence index" rows={3} />

  if (decisions.length === 0) {
    return <EmptyState title="No decisions to trace" hint="The decision engine has not produced any decisions yet." />
  }

  const current = decisions.find((d) => d.decision_id === selected)

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-bold tracking-tight text-ink-900">Evidence trace</h1>
        <p className="mt-1 text-xs leading-relaxed text-ink-500">
          Every citation below was retrieved from the operational database and resolved back to a real primary key before
          being attached to a decision. Fabricated references are structurally impossible: the retriever drops any hit it
          cannot verify.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <Card title="Select a decision" subtitle="Newest first" className="!p-0">
          <ul className="max-h-[70vh] divide-y divide-ink-100 overflow-y-auto">
            {decisions.map((d) => (
              <li key={d.decision_id}>
                <button
                  onClick={() => setSelected(d.decision_id)}
                  className={`flex w-full flex-wrap items-center gap-2 px-4 py-3 text-left transition-colors ${
                    selected === d.decision_id ? 'bg-ink-900 text-white' : 'hover:bg-ink-50'
                  }`}
                >
                  <span className={`chip px-1.5 py-0.5 text-[10px] ${
                    selected === d.decision_id
                      ? 'border-white/40 bg-white/10 text-white'
                      : d.priority === 'HIGH'
                        ? 'border-red-300 bg-red-50 text-red-700'
                        : d.priority === 'MEDIUM'
                          ? 'border-amber-300 bg-amber-50 text-amber-800'
                          : 'border-emerald-300 bg-emerald-50 text-emerald-800'
                  }`}>
                    {d.priority}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-sm font-semibold">{d.customer_name}</span>
                  <span className={`mono text-[10px] ${selected === d.decision_id ? 'text-white/70' : 'text-ink-400'}`}>
                    {d.priority_score.toFixed(1)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Card>

        <div className="space-y-5">
          {current && (
            <Card
              title={`${current.customer_name} · ${current.decision_id}`}
              subtitle={current.decision_text}
              action={<Link to={`/customers/${current.customer_id}`} className="text-xs font-semibold text-ink-700 hover:underline">Account →</Link>}
            >
              <div className="flex flex-wrap items-center gap-3">
                <PriorityChip priority={current.priority} score={current.priority_score} />
                <span className="text-xs text-ink-500">{dateStr(current.generated_at)}</span>
                <span className="text-xs text-ink-500">· status {current.status}</span>
              </div>

              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <div>
                  <div className="kv-label mb-1.5">Evidence by source</div>
                  <BarList data={breakdown} color="#1b2130" />
                </div>
                <div>
                  <div className="kv-label mb-1.5">Filter evidence</div>
                  <div className="flex flex-wrap gap-1.5">
                    <button
                      onClick={() => setFilter('')}
                      className={`rounded-md px-2.5 py-1 text-[11px] font-semibold ${filter === '' ? 'bg-ink-900 text-white' : 'border border-ink-200 bg-white text-ink-600'}`}
                    >
                      All ({items?.length ?? 0})
                    </button>
                    {breakdown.map((b) => (
                      <button
                        key={b.label}
                        onClick={() => setFilter(b.label)}
                        className={`rounded-md px-2.5 py-1 text-[11px] font-semibold ${filter === b.label ? 'bg-ink-900 text-white' : 'border border-ink-200 bg-white text-ink-600'}`}
                      >
                        {b.label} ({b.value})
                      </button>
                    ))}
                  </div>
                  <p className="mt-3 text-[11px] leading-relaxed text-ink-500">
                    Retrieval runs a vector similarity search over indexed business notes and support tickets, then merges
                    deterministic analytics evidence computed directly from the sales and usage tables.
                  </p>
                </div>
              </div>
            </Card>
          )}

          {!filtered ? (
            <LoadingState label="Loading evidence trace" rows={3} />
          ) : filtered.length === 0 ? (
            <EmptyState title="No evidence of this type on this decision" />
          ) : (
            <ol className="space-y-3">
              {filtered.map((ev: any) => (
                <li key={`${ev.source_table}-${ev.source_id}`} className="card p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-ink-900 text-[10px] font-bold text-white">
                      {ev.rank}
                    </span>
                    <span className={`chip px-1.5 py-0.5 text-[10px] ${SOURCE_STYLES[ev.source_table] ?? 'border-ink-300 bg-ink-100 text-ink-700'}`}>
                      {ev.source_table}
                    </span>
                    <span className="mono font-semibold text-ink-800">{ev.source_id}</span>
                    <span className="chip border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[9px] text-emerald-700">verified</span>
                    <span className="ml-auto text-[10px] text-ink-400">{relativeDays(ev.occurred_on)}</span>
                  </div>
                  <div className="mt-2 text-sm font-semibold text-ink-900">{ev.title}</div>
                  <p className="mt-1.5 text-xs leading-relaxed text-ink-700">{ev.snippet}</p>
                  <div className="mt-2 flex flex-wrap gap-3 border-t border-ink-100 pt-2 text-[10px] text-ink-400">
                    <span>retrieval: {ev.retrieval_method}</span>
                    <span>score: {ev.score.toFixed(3)}</span>
                    <span>type: {ev.evidence_type}</span>
                    {ev.occurred_on && <span>occurred: {ev.occurred_on}</span>}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </div>
  )
}
