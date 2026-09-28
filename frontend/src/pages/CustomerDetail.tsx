import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { dateStr, money, num, pct, priorityStyle } from '../lib/format'
import DecisionCard from '../components/DecisionCard'
import {
  BarList, Card, ConfidenceMeter, EmptyState, ErrorState, KpiCard,
  LineChart, LoadingState, PriorityChip, ScoreBar, SignalRow, StatusChip,
} from '../components/ui'

export default function CustomerDetail() {
  const { customerId = '' } = useParams()
  const [data, setData] = useState<any>(null)
  const [decision, setDecision] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<'trace' | 'timeline' | 'tickets' | 'notes'>('trace')

  function load() {
    setError(null)
    api
      .customer(customerId)
      .then((detail) => {
        setData(detail)
        if (detail.latest_decision_id) {
          return api.decision(detail.latest_decision_id).then(setDecision)
        }
        return null
      })
      .catch((e) => setError(e.message))
  }

  useEffect(() => {
    setData(null)
    setDecision(null)
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customerId])

  if (error) return <ErrorState message={error} onRetry={load} />
  if (!data) return <LoadingState label={`Loading ${customerId}`} rows={4} />

  const c = data.customer
  const s = priorityStyle(data.priority)

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-xs text-ink-500">
        <Link to="/customers" className="font-medium hover:underline">Customers</Link>
        <span>/</span>
        <span className="font-semibold text-ink-800">{c.customer_name}</span>
      </div>

      <section className={`card border-l-4 ${s.bar.replace('bg-', 'border-l-')}`}>
        <div className="flex flex-wrap items-start justify-between gap-4 p-5">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <PriorityChip priority={data.priority} score={data.priority_score} />
              <StatusChip status={c.status} />
              <span className="chip border-ink-200 bg-ink-50 px-1.5 py-0.5 text-[10px] text-ink-600">{c.segment}</span>
              <span className="chip border-ink-200 bg-ink-50 px-1.5 py-0.5 text-[10px] text-ink-600">{c.region}</span>
            </div>
            <h1 className="mt-2 text-xl font-bold tracking-tight text-ink-900">{c.customer_name}</h1>
            <p className="mt-1 text-xs text-ink-500">
              <span className="mono">{c.customer_id}</span> · {c.industry} · owner {c.owner} · onboarded {dateStr(data.onboarded_on)}
            </p>
          </div>
          <div className="w-full max-w-xs shrink-0">
            <div className="flex items-center justify-between text-[11px] text-ink-500">
              <span className="font-semibold uppercase tracking-wider">Priority score</span>
              <span className="font-mono text-base font-bold text-ink-900">{data.priority_score.toFixed(1)}/100</span>
            </div>
            <div className="mt-1.5"><ScoreBar score={data.priority_score} priority={data.priority} /></div>
            <div className="mt-2"><ConfidenceMeter value={data.confidence} label="confidence" /></div>
          </div>
        </div>
      </section>

      <section className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
        {data.kpis.map((kpi: any) => (
          <KpiCard key={kpi.key} kpi={kpi} />
        ))}
      </section>

      {data.reasons.length > 0 && (
        <Card title="Why the engine scored this account here" subtitle="Each reason is generated from the computed signal value">
          <ul className="space-y-2">
            {data.reasons.map((reason: string, i: number) => (
              <li key={i} className="flex gap-2 text-sm leading-relaxed text-ink-700">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-ink-400" />
                <span>{reason}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Revenue (weekly, 90d window)" subtitle="Booked revenue per week from the sales ledger">
          <LineChart series={data.revenue_series} color="#1b2130" />
          <div className="mt-3 flex flex-wrap gap-4 text-[11px] text-ink-500">
            <span>90-day revenue <strong className="text-ink-800">{money(data.kpis.find((k: any) => k.key === 'revenue_90d')?.value)}</strong></span>
            <span>Δ 30d vs prior 30d <strong className={data.kpis.find((k: any) => k.key === 'revenue_90d')?.delta_pct < 0 ? 'text-red-600' : 'text-emerald-600'}>{pct(data.kpis.find((k: any) => k.key === 'revenue_90d')?.delta_pct)}</strong></span>
          </div>
        </Card>
        <Card title="Product usage (daily active users)" subtitle="Telemetry from the usage_records table">
          <LineChart series={data.usage_series} color="#0f766e" valueFormat={(v) => `${v.toFixed(0)}`} />
          <div className="mt-3 flex flex-wrap gap-4 text-[11px] text-ink-500">
            <span>14-day avg <strong className="text-ink-800">{num(data.kpis.find((k: any) => k.key === 'usage')?.value, 1)} users</strong></span>
            <span>Δ 14d vs prior 14d <strong className={data.kpis.find((k: any) => k.key === 'usage')?.delta_pct < 0 ? 'text-red-600' : 'text-emerald-600'}>{pct(data.kpis.find((k: any) => k.key === 'usage')?.delta_pct)}</strong></span>
          </div>
        </Card>
      </div>

      <section>
        <div className="mb-3 flex flex-wrap gap-1.5">
          {([
            ['trace', 'Signal breakdown'],
            ['timeline', `Timeline (${data.timeline.length})`],
            ['tickets', `Support tickets (${data.tickets.length})`],
            ['notes', `Business notes (${data.notes.length})`],
          ] as const).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                tab === key ? 'bg-ink-900 text-white' : 'border border-ink-200 bg-white text-ink-600 hover:bg-ink-50'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <Card>
          {tab === 'trace' && (
            data.signals.length === 0
              ? <EmptyState title="No signals available" />
              : <div>{data.signals.map((sig: any) => <SignalRow key={sig.key} signal={sig} />)}</div>
          )}

          {tab === 'timeline' && (
            data.timeline.length === 0 ? <EmptyState title="No activity recorded" /> : (
              <ol className="relative space-y-4 border-l border-ink-200 pl-5">
                {data.timeline.map((item: any, i: number) => (
                  <li key={i} className="relative">
                    <span className={`absolute -left-[26px] mt-1 h-2.5 w-2.5 rounded-full border-2 border-white ${
                      item.type === 'ticket' ? 'bg-red-500' : item.type === 'note' ? 'bg-amber-500' : 'bg-emerald-500'
                    }`} />
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="mono text-ink-400">{item.date}</span>
                      <span className="chip border-ink-200 bg-ink-50 px-1.5 py-0.5 text-[9px] text-ink-600">{item.type}</span>
                    </div>
                    <div className="mt-1 text-xs font-semibold text-ink-800">{item.title}</div>
                    <p className="mt-0.5 text-[11px] leading-relaxed text-ink-600">{item.detail}</p>
                  </li>
                ))}
              </ol>
            )
          )}

          {tab === 'tickets' && (
            data.tickets.length === 0 ? <EmptyState title="No support tickets on record" hint="This account has never raised a ticket." /> : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse">
                  <thead>
                    <tr>{['Ticket', 'Issue', 'Severity', 'Status', 'Created', 'Age', 'Assignee'].map((h) => (
                      <th key={h} className="table-head px-3 py-2 whitespace-nowrap">{h}</th>
                    ))}</tr>
                  </thead>
                  <tbody>
                    {data.tickets.map((t: any) => (
                      <tr key={t.ticket_id} className="hover:bg-ink-50">
                        <td className="table-cell mono font-semibold">{t.ticket_id}</td>
                        <td className="table-cell text-xs text-ink-700">{t.issue}</td>
                        <td className="table-cell">
                          <span className={`chip px-1.5 py-0.5 text-[10px] ${
                            t.severity === 'critical' ? 'border-red-300 bg-red-50 text-red-700'
                            : t.severity === 'high' ? 'border-amber-300 bg-amber-50 text-amber-800'
                            : 'border-ink-300 bg-ink-100 text-ink-700'
                          }`}>{t.severity}</span>
                        </td>
                        <td className="table-cell"><StatusChip status={t.status} /></td>
                        <td className="table-cell text-xs text-ink-600">{dateStr(t.created_at)}</td>
                        <td className="table-cell font-mono text-xs">{t.age_days}d</td>
                        <td className="table-cell text-xs text-ink-600">{t.assignee}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          )}

          {tab === 'notes' && (
            data.notes.length === 0 ? <EmptyState title="No business notes on record" /> : (
              <ul className="space-y-3">
                {data.notes.map((n: any) => (
                  <li key={n.note_id} className="rounded-md border border-ink-200 bg-white p-3.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="mono font-semibold">{n.note_id}</span>
                      <span className="chip border-ink-200 bg-ink-50 px-1.5 py-0.5 text-[10px] text-ink-600">
                        {n.note_type.replace(/_/g, ' ')}
                      </span>
                      <span className="text-[10px] text-ink-400">{n.author_role} · {dateStr(n.date)}</span>
                    </div>
                    <p className="mt-2 text-sm leading-relaxed text-ink-700">{n.note_text}</p>
                  </li>
                ))}
              </ul>
            )
          )}
        </Card>
      </section>

      {decision && (
        <section>
          <h2 className="mb-3 text-sm font-bold uppercase tracking-wider text-ink-500">
            Latest decision · {decision.decision_id}
          </h2>
          <DecisionCard
            decision={decision}
            defaultOpen
            onReviewed={(id, status) => {
              setDecision((d: any) => (d ? { ...d, status } : d))
            }}
          />
        </section>
      )}

      {!decision && (
        <EmptyState
          title="No decision generated for this account yet"
          hint="Decisions are produced by the decision engine. Run the seed and regenerate steps from the documentation."
        />
      )}
    </div>
  )
}
