import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { dateTimeStr, money, priorityStyle } from '../lib/format'
import { ConfidenceMeter, PriorityChip, ScoreBar, SignalRow, StatusChip } from './ui'

/**
 * A decision card. Approve/Reject are wired to the real backend and persist;
 * the returned status is reflected immediately and the button pair locks.
 */
export default function DecisionCard({
  decision,
  defaultOpen = false,
  onReviewed,
}: {
  decision: any
  defaultOpen?: boolean
  onReviewed?: (id: string, status: string) => void
}) {
  const [open, setOpen] = useState(defaultOpen)
  const [status, setStatus] = useState<string>(decision.status)
  const [busy, setBusy] = useState<'approve' | 'reject' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reviewed, setReviewed] = useState<any>(decision.human_decision ?? null)
  const [traceOpen, setTraceOpen] = useState(false)

  const s = priorityStyle(decision.priority)

  async function review(kind: 'approve' | 'reject') {
    setBusy(kind)
    setError(null)
    try {
      const result = kind === 'approve' ? await api.approve(decision.decision_id) : await api.reject(decision.decision_id)
      setStatus(result.status)
      setReviewed({ decision: result.human_decision, actor: 'sales.manager@example.com', timestamp: result.timestamp })
      onReviewed?.(decision.decision_id, result.status)
    } catch (e: any) {
      setError(e?.message ?? 'Review failed')
    } finally {
      setBusy(null)
    }
  }

  return (
    <article className={`card overflow-hidden border-l-4 ${s.bar.replace('bg-', 'border-l-')}`}>
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-ink-100 px-5 py-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <PriorityChip priority={decision.priority} score={decision.priority_score} />
            <StatusChip status={status} />
            {decision.insufficient_evidence && (
              <span className="chip border-ink-300 bg-ink-100 px-1.5 py-0.5 text-[10px] text-ink-600">insufficient evidence</span>
            )}
            {decision.llm_used && (
              <span className="chip border-violet-300 bg-violet-50 px-1.5 py-0.5 text-[10px] text-violet-700">LLM-phrased</span>
            )}
          </div>
          <h3 className="mt-2 text-base font-bold tracking-tight text-ink-900">
            <Link to={`/customers/${decision.customer.customer_id}`} className="hover:underline">
              {decision.customer.customer_name}
            </Link>
            <span className="ml-2 font-mono text-xs font-normal text-ink-400">{decision.customer.customer_id}</span>
          </h3>
          <p className="mt-1 text-sm leading-relaxed text-ink-700">{decision.decision_text}</p>
        </div>
        <div className="shrink-0 text-right">
          <div className="kv-label">Decision id</div>
          <div className="mono mt-0.5 font-semibold">{decision.decision_id}</div>
          <div className="mt-1.5 text-[11px] text-ink-400">{dateTimeStr(decision.generated_at)}</div>
        </div>
      </header>

      <div className="grid gap-4 border-b border-ink-100 bg-ink-50/60 px-5 py-3 sm:grid-cols-4">
        <div>
          <div className="kv-label">Priority score</div>
          <div className="mt-1 flex items-center gap-2">
            <span className={`text-lg font-bold tabular-nums ${s.text}`}>{decision.priority_score.toFixed(1)}</span>
            <span className="text-[10px] text-ink-400">/100</span>
          </div>
          <div className="mt-1.5"><ScoreBar score={decision.priority_score} priority={decision.priority} /></div>
          <div className="mt-1 text-[10px] text-ink-500">{decision.priority_score_band}</div>
        </div>
        <div>
          <div className="kv-label">Confidence</div>
          <div className="mt-1.5"><ConfidenceMeter value={decision.confidence} label={decision.confidence_label} /></div>
          <div className="mt-1.5 text-[10px] text-ink-500">
            {decision.signals.filter((sig: any) => sig.has_data).length}/{decision.signals.length} signals measurable
          </div>
        </div>
        <div>
          <div className="kv-label">Account value</div>
          <div className="mt-1 text-sm font-semibold text-ink-900">{money(decision.customer.account_value)}</div>
          <div className="mt-1.5 text-[10px] text-ink-500">
            {decision.customer.segment} · {decision.customer.region}
          </div>
        </div>
        <div>
          <div className="kv-label">Engine</div>
          <div className="mt-1 text-sm font-semibold text-ink-900">{decision.engine_mode}</div>
          <div className="mt-1.5 text-[10px] text-ink-500">{decision.evidence.length} verified evidence record(s)</div>
        </div>
      </div>

      <div className="px-5 py-4">
        <button className="flex w-full items-center justify-between text-left" onClick={() => setOpen((v) => !v)}>
          <span className="card-title">Reason · key signals</span>
          <span className="text-xs text-ink-500">{open ? 'Hide' : 'Show'}</span>
        </button>

        {open && (
          <div className="mt-4 space-y-5">
            <div>
              <div className="kv-label mb-2">Why this priority</div>
              <ul className="space-y-2">
                {decision.reasons.map((reason: string, i: number) => (
                  <li key={i} className="flex gap-2 text-sm leading-relaxed text-ink-700">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-ink-400" />
                    <span>{reason}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <div className="kv-label mb-1">Weighted signal breakdown</div>
              <div className="rounded-md border border-ink-200 bg-white px-3">
                {decision.signals.map((sig: any) => (
                  <SignalRow key={sig.key} signal={sig} />
                ))}
              </div>
            </div>

            <div>
              <button className="flex w-full items-center justify-between text-left" onClick={() => setTraceOpen((v) => !v)}>
                <span className="kv-label">Evidence trace · {decision.evidence.length} record(s)</span>
                <span className="text-xs text-ink-500">{traceOpen ? 'Hide' : 'Show'}</span>
              </button>
              {traceOpen && (
                <ol className="mt-3 space-y-2">
                  {decision.evidence.map((ev: any) => (
                    <li key={`${ev.source_table}-${ev.source_id}`} className="rounded-md border border-ink-200 bg-white p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-ink-900 text-[10px] font-bold text-white">
                          {ev.rank}
                        </span>
                        <span className="chip border-ink-200 bg-ink-50 px-1.5 py-0.5 text-[10px] text-ink-600">
                          {ev.source_table}
                        </span>
                        <span className="mono font-semibold text-ink-800">{ev.source_id}</span>
                        <span className="ml-auto chip border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[9px] text-emerald-700">
                          verified
                        </span>
                      </div>
                      <div className="mt-1.5 text-xs font-semibold text-ink-800">{ev.title}</div>
                      <p className="mt-1 text-[11px] leading-relaxed text-ink-600">{ev.snippet}</p>
                      <div className="mt-1.5 flex flex-wrap gap-3 text-[10px] text-ink-400">
                        <span>retrieval: {ev.retrieval_method}</span>
                        <span>score: {ev.score.toFixed(3)}</span>
                        {ev.occurred_on && <span>occurred: {ev.occurred_on}</span>}
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </div>
        )}
      </div>

      <footer className="border-t border-ink-100 bg-white px-5 py-4">
        <div className="rounded-md border border-ink-200 bg-ink-50/70 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="chip border-ink-900 bg-ink-900 px-1.5 py-0.5 text-[10px] text-white">
              {decision.recommended_action.label}
            </span>
            <span className="text-[10px] text-ink-500">
              owner {decision.recommended_action.owner} · SLA {decision.recommended_action.sla_hours}h
            </span>
          </div>
          <p className="mt-2 text-sm leading-relaxed text-ink-700">{decision.recommended_action.rationale}</p>
        </div>

        <div className="mt-3">
          <button
            className="flex w-full items-center justify-between text-left"
            onClick={() => setTraceOpen((v) => !v)}
            aria-expanded={traceOpen}
          >
            <span className="kv-label">Explainability trace</span>
            <span className="text-xs text-ink-500">{traceOpen ? 'Hide' : 'Show'}</span>
          </button>
        </div>

        <p className="mt-2 whitespace-pre-line text-[11px] leading-relaxed text-ink-500">{decision.explanation}</p>

        <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-ink-100 pt-4">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-500">Human approval</span>
          <button className="btn-approve" disabled={status !== 'pending' || busy !== null} onClick={() => review('approve')}>
            {busy === 'approve' ? 'Approving…' : status === 'approved' ? '✓ Approved' : 'Approve'}
          </button>
          <button className="btn-reject" disabled={status !== 'pending' || busy !== null} onClick={() => review('reject')}>
            {busy === 'reject' ? 'Rejecting…' : status === 'rejected' ? '✕ Rejected' : 'Reject'}
          </button>

          {status !== 'pending' && reviewed && (
            <span className="text-[11px] text-ink-500">
              AI recommendation · human decision <strong className="text-ink-800">{reviewed.decision}</strong> ·{' '}
              {dateTimeStr(reviewed.timestamp)} · {reviewed.actor}
            </span>
          )}
          {status === 'pending' && <span className="text-[11px] text-ink-400">AI recommendation is not final until reviewed.</span>}
        </div>

        {error && <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>}
      </footer>
    </article>
  )
}
