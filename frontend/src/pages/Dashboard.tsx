import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { compactMoney, dateStr, money, num, priorityStyle, relativeDays } from '../lib/format'
import {
  BarList, Card, ConfidenceMeter, Donut, EmptyState, ErrorState, KpiCard,
  LineChart, LoadingState, PriorityChip, ScoreBar, StatusChip,
} from '../components/ui'

export default function Dashboard() {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  function load() {
    setLoading(true)
    setError(null)
    api
      .dashboard()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  if (loading) return <LoadingState label="Loading decision dashboard" rows={4} />
  if (error) return <ErrorState message={error} onRetry={load} />
  if (!data) return <EmptyState title="No dashboard data" />

  return (
    <div className="space-y-6">
      {/* headline */}
      <section className="card border-ink-300 bg-white">
        <div className="flex flex-wrap items-start justify-between gap-4 p-5">
          <div className="min-w-0 max-w-3xl">
            <div className="flex items-center gap-2">
              <span className="chip border-ink-900 bg-ink-900 px-2 py-0.5 text-[10px] text-white">What requires attention now</span>
              <span className="text-[11px] text-ink-500">
                business date {dateStr(data.reference_date)} · generated {dateStr(data.generated_at)}
              </span>
            </div>
            <h1 className="mt-3 text-xl font-bold leading-snug tracking-tight text-ink-900">{data.headline}</h1>
            <p className="mt-2 text-xs leading-relaxed text-ink-500">
              Every figure below is computed from the operational database by the analytics layer, not asserted by a
              language model. Each recommendation ships with a verified evidence trace and waits for human approval.
            </p>
          </div>
          <Link to="/ask" className="btn-primary shrink-0">
            Ask DeciTrace
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M5 12h14M13 6l6 6-6 6" />
            </svg>
          </Link>
        </div>
      </section>

      {/* KPIs */}
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
        {data.kpis.map((kpi: any) => (
          <KpiCard key={kpi.key} kpi={kpi} />
        ))}
      </section>

      <div className="grid gap-6 xl:grid-cols-3">
        {/* attention queue */}
        <section className="xl:col-span-2">
          <Card
            title="Attention queue — prioritised accounts"
            subtitle="Ranked by the weighted decision score. Open the trace to see the exact evidence."
            action={<Link to="/decisions" className="text-xs font-semibold text-ink-700 hover:underline">All decisions →</Link>}
          >
            {data.attention_queue.length === 0 ? (
              <EmptyState title="Nothing is breaching the priority threshold" hint="No customer currently scores MEDIUM or higher." />
            ) : (
              <ul className="space-y-2.5">
                {data.attention_queue.map((item: any) => {
                  const s = priorityStyle(item.priority)
                  return (
                    <li key={item.decision_id} className={`rounded-md border border-ink-200 border-l-4 bg-white p-3.5 ${s.bar.replace('bg-', 'border-l-')}`}>
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <PriorityChip priority={item.priority} score={item.priority_score} />
                            <StatusChip status={item.status} />
                            <Link
                              to={`/customers/${item.customer_id}`}
                              className="text-sm font-bold tracking-tight text-ink-900 hover:underline"
                            >
                              {item.customer_name}
                            </Link>
                            <span className="mono text-ink-400">{item.customer_id}</span>
                          </div>
                          <p className="mt-1.5 text-xs leading-relaxed text-ink-700">{item.headline}</p>
                          <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-ink-500">{item.top_reason}</p>
                          <div className="mt-1.5 flex flex-wrap gap-3 text-[10px] text-ink-500">
                            <span>value {money(item.account_value)}</span>
                            <span>action: {item.action_label}</span>
                            <span>{item.decision_id}</span>
                          </div>
                        </div>
                        <div className="w-40 shrink-0">
                          <ConfidenceMeter value={item.confidence} />
                          <div className="mt-2"><ScoreBar score={item.priority_score} priority={item.priority} /></div>
                        </div>
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </Card>
        </section>

        {/* distributions */}
        <section className="space-y-6">
          <Card title="Decision distribution" subtitle="Priority banding across the book">
            <Donut data={data.priority_distribution} />
          </Card>
          <Card title="Open business issues" subtitle="Unresolved support tickets by severity">
            <BarList data={data.issue_distribution} color="#dc2626" />
          </Card>
        </section>
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <section className="xl:col-span-2">
          <Card title="Revenue trend" subtitle="Weekly booked revenue across the book (last 6 months)">
            <LineChart series={data.revenue_trend.map((r: any) => ({ date: r.week, value: r.revenue }))} />
          </Card>
        </section>
        <Card title="Top recommended actions" subtitle="What the engine is telling the team to do">
          <BarList data={data.action_distribution} color="#0f766e" />
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Recent AI decisions" subtitle="Newest generated decisions, all awaiting review" action={<Link to="/decisions" className="text-xs font-semibold text-ink-700 hover:underline">Open →</Link>}>
          {data.recent_decisions.length === 0 ? (
            <EmptyState title="No decisions yet" />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr>
                    {['Customer', 'Priority', 'Score', 'Recommended action', 'Status'].map((h) => (
                      <th key={h} className="table-head px-3 py-2">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.recent_decisions.map((d: any) => (
                    <tr key={d.decision_id} className="hover:bg-ink-50">
                      <td className="table-cell">
                        <Link to={`/customers/${d.customer_id}`} className="font-medium text-ink-900 hover:underline">
                          {d.customer_name}
                        </Link>
                        <div className="mono text-ink-400">{d.decision_id}</div>
                      </td>
                      <td className="table-cell"><PriorityChip priority={d.priority} size="sm" /></td>
                      <td className="table-cell font-mono tabular-nums">{d.priority_score.toFixed(1)}</td>
                      <td className="table-cell text-xs text-ink-600">{d.action_type.replace(/_/g, ' ')}</td>
                      <td className="table-cell"><StatusChip status={d.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="Recent evidence retrieved" subtitle="Verbatim rows pulled from notes and tickets by the vector index">
          {data.recent_evidence.length === 0 ? (
            <EmptyState title="No evidence retrieved yet" />
          ) : (
            <ul className="space-y-2.5">
              {data.recent_evidence.map((ev: any) => (
                <li key={`${ev.source_table}-${ev.source_id}-${ev.id}`} className="rounded-md border border-ink-200 bg-white p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="chip border-ink-200 bg-ink-50 px-1.5 py-0.5 text-[10px] text-ink-600">{ev.source_table}</span>
                    <span className="mono font-semibold">{ev.source_id}</span>
                    <span className="ml-auto text-[10px] text-ink-400">{relativeDays(ev.occurred_on)}</span>
                  </div>
                  <div className="mt-1.5 text-xs font-semibold text-ink-800">{ev.title}</div>
                  <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-ink-600">{ev.snippet}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Decision pipeline" subtitle="How each recommendation was produced — nothing is generated by an LLM alone">
        <ol className="grid gap-3 md:grid-cols-4">
          {data.pipeline.map((step: any) => (
            <li key={step.step} className="rounded-md border border-ink-200 bg-ink-50/60 p-3">
              <div className="flex items-center gap-2">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-ink-900 text-[10px] font-bold text-white">
                  {step.step}
                </span>
                <span className="text-xs font-bold text-ink-800">{step.name}</span>
              </div>
              <p className="mt-1.5 text-[11px] leading-relaxed text-ink-500">{step.detail}</p>
            </li>
          ))}
        </ol>
      </Card>

      <Card title="Data health" subtitle={`Analysed window ${data.data_health.window_start} → ${data.data_health.window_end}`}>
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {[
            ['customers', data.data_health.customers],
            ['sales rows', num(data.data_health.sales_rows)],
            ['usage rows', num(data.data_health.usage_rows)],
            ['ticket rows', num(data.data_health.ticket_rows)],
            ['note rows', num(data.data_health.note_rows)],
            ['history (days)', num(data.data_health.history_days)],
          ].map(([label, value]: any) => (
            <div key={label}>
              <dt className="kv-label">{label}</dt>
              <dd className="mt-0.5 text-lg font-bold tabular-nums text-ink-900">{value}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-4 text-[11px] text-ink-500">
          Total 90-day revenue in scope: <strong className="text-ink-800">{compactMoney(data.kpis.find((k: any) => k.key === 'revenue_at_risk')?.value)}</strong> across
          HIGH and MEDIUM priority accounts.
        </p>
      </Card>
    </div>
  )
}
