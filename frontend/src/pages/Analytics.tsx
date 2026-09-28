import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { dateTimeStr, num } from '../lib/format'
import { BarList, Card, EmptyState, ErrorState, LoadingState, Table } from '../components/ui'

const CASE_TYPE_ORDER = ['normal', 'high_risk', 'multi_signal', 'ambiguous', 'insufficient_evidence']

function MetricTile({ label, value, hint, tone = 'default' }: { label: string; value: string; hint?: string; tone?: 'default' | 'good' | 'warn' }) {
  const toneCls = tone === 'good' ? 'text-emerald-700' : tone === 'warn' ? 'text-amber-700' : 'text-ink-900'
  return (
    <div className="card p-4">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-500">{label}</div>
      <div className={`mt-1.5 text-2xl font-bold tabular-nums tracking-tight ${toneCls}`}>{value}</div>
      {hint && <div className="mt-1 text-[11px] leading-relaxed text-ink-500">{hint}</div>}
    </div>
  )
}

export default function Analytics() {
  const [evaluation, setEvaluation] = useState<any>(null)
  const [dashboard, setDashboard] = useState<any>(null)
  const [health, setHealth] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [runMessage, setRunMessage] = useState<string | null>(null)

  function loadAll() {
    setError(null)
    Promise.all([api.evaluation(), api.dashboard(), api.health()])
      .then(([e, d, h]) => {
        setEvaluation(e)
        setDashboard(d)
        setHealth(h)
      })
      .catch((e) => setError(e.message))
  }

  useEffect(loadAll, [])

  async function runEvaluation() {
    setRunning(true)
    setRunMessage(null)
    try {
      const result = await api.evaluate()
      setEvaluation(result)
      setRunMessage(result.message)
      loadAll()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  if (error) return <ErrorState message={error} onRetry={loadAll} />
  if (!evaluation || !dashboard) return <LoadingState label="Loading analytics" rows={4} />

  const executed = evaluation.executed === true
  const metrics = evaluation.metrics

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold tracking-tight text-ink-900">Analytics & Evaluation</h1>
          <p className="mt-1 text-xs leading-relaxed text-ink-500">
            Portfolio analytics computed from the operational database, plus the measured output of the evaluation
            harness. No benchmark figure is displayed unless the harness has actually executed against this database.
          </p>
        </div>
        <button className="btn-primary" onClick={runEvaluation} disabled={running}>
          {running ? 'Running evaluation…' : 'Run evaluation'}
        </button>
      </div>

      {runMessage && (
        <div className="card border-emerald-200 bg-emerald-50 px-4 py-3 text-xs text-emerald-800">{runMessage}</div>
      )}

      {/* ---------------- evaluation ---------------- */}
      <Card
        title="Evaluation harness"
        subtitle="5 synthetic case types executed through the live decision pipeline"
        action={<span className="text-[11px] text-ink-500">{executed ? evaluation.run_id : 'not executed'}</span>}
      >
        {!executed ? (
          <div className="rounded-md border border-amber-300 bg-amber-50 p-5">
            <div className="flex items-center gap-2">
              <span className="chip border-amber-400 bg-amber-100 px-2 py-0.5 text-[10px] text-amber-900">Evaluation pending</span>
            </div>
            <p className="mt-3 text-sm font-semibold text-amber-900">Evaluation pending</p>
            <p className="mt-1.5 text-xs leading-relaxed text-amber-800">
              {evaluation.message ||
                'The harness has not been executed for this database. Decision accuracy, evidence hit rate and response time are therefore not reported — presenting them would mean inventing numbers.'}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button className="btn-primary" onClick={runEvaluation} disabled={running}>
                {running ? 'Running…' : 'Execute evaluation now'}
              </button>
            </div>
            <p className="mt-3 text-[11px] text-amber-800">
              Equivalent CLI command: <code className="mono rounded bg-amber-100 px-1.5 py-0.5">python -m app.evaluation.harness</code>
            </p>
            <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {CASE_TYPE_ORDER.map((t) => (
                <div key={t} className="rounded-md border border-amber-200 bg-white/70 p-3">
                  <div className="text-xs font-bold text-amber-900">{t.replace(/_/g, ' ')}</div>
                  <div className="mt-1 text-[10px] text-amber-800">
                    {t === 'normal' && 'Healthy accounts — expecting LOW'}
                    {t === 'high_risk' && 'Churn risk — expecting HIGH'}
                    {t === 'multi_signal' && 'Several independent signals aligned'}
                    {t === 'ambiguous' && 'A single dip that is plausibly seasonal'}
                    {t === 'insufficient_evidence' && 'New account, thin history'}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-3 text-[11px] text-ink-500">
              <span className="chip border-emerald-300 bg-emerald-50 px-2 py-0.5 text-[10px] text-emerald-800">Executed</span>
              <span>run {evaluation.run_id}</span>
              <span>· {dateTimeStr(evaluation.executed_at)}</span>
              <span>· {num(metrics.total_cases)} cases</span>
              <span>· {num(evaluation.duration_ms, 0)} ms total</span>
              <span>· engine {evaluation.engine_mode}</span>
            </div>

            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <MetricTile
                label="Decision accuracy"
                value={`${(metrics.decision_accuracy * 100).toFixed(1)}%`}
                hint={`Exact priority match vs the synthetic ground-truth archetype (${num(metrics.total_cases)} cases)`}
                tone={metrics.decision_accuracy >= 0.7 ? 'good' : 'warn'}
              />
              <MetricTile
                label="Adjacent accuracy"
                value={`${(metrics.adjacent_accuracy * 100).toFixed(1)}%`}
                hint="Prediction within one priority band of the expected band"
              />
              <MetricTile
                label="Evidence hit rate"
                value={`${(metrics.evidence_hit_rate * 100).toFixed(1)}%`}
                hint="Cases that returned at least one verified evidence record"
                tone={metrics.evidence_hit_rate >= 0.9 ? 'good' : 'warn'}
              />
              <MetricTile
                label="Evidence verification"
                value={`${(metrics.evidence_verification_rate * 100).toFixed(1)}%`}
                hint={`Verified citations ÷ all citations (${num(metrics.avg_evidence_per_case, 2)} per case)`}
                tone={metrics.evidence_verification_rate === 1 ? 'good' : 'warn'}
              />
              <MetricTile
                label="Avg response time"
                value={`${num(metrics.avg_response_ms, 0)} ms`}
                hint="Mean end-to-end pipeline latency per case"
              />
              <MetricTile
                label="P95 response time"
                value={`${num(metrics.p95_response_ms, 0)} ms`}
                hint="95th percentile latency — the slow tail"
              />
              <MetricTile
                label="Escalation failure rate"
                value={`${(metrics.escalation_failure_rate * 100).toFixed(1)}%`}
                hint="Cases expected HIGH that were scored LOW — a missed escalation"
                tone={metrics.escalation_failure_rate === 0 ? 'good' : 'warn'}
              />
              <MetricTile
                label="Insufficient-evidence rate"
                value={`${(metrics.insufficient_evidence_rate * 100).toFixed(1)}%`}
                hint="Cases the engine refused to decide because evidence was too thin"
              />
            </div>

            <div className="grid gap-5 lg:grid-cols-2">
              <div>
                <div className="kv-label mb-2">Measured by case type</div>
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse">
                    <thead>
                      <tr>{['Case type', 'n', 'Accuracy', 'Evidence hit', 'Avg latency'].map((h) => (
                        <th key={h} className="table-head px-3 py-2 whitespace-nowrap">{h}</th>
                      ))}</tr>
                    </thead>
                    <tbody>
                      {CASE_TYPE_ORDER.filter((t) => metrics.by_case_type[t]?.cases).map((t) => {
                        const b = metrics.by_case_type[t]
                        return (
                          <tr key={t} className="hover:bg-ink-50">
                            <td className="table-cell text-xs font-semibold text-ink-800">
                              {t.replace(/_/g, ' ')}
                              <div className="text-[10px] font-normal text-ink-400">{b.label}</div>
                            </td>
                            <td className="table-cell font-mono text-xs">{b.cases}</td>
                            <td className="table-cell font-mono text-xs font-semibold">
                              {(b.decision_accuracy * 100).toFixed(1)}%
                            </td>
                            <td className="table-cell font-mono text-xs">{(b.evidence_hit_rate * 100).toFixed(1)}%</td>
                            <td className="table-cell font-mono text-xs">{num(b.avg_latency_ms, 0)} ms</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              <div>
                <div className="kv-label mb-2">Expected vs predicted priority per case</div>
                <Table head={['Case', 'Customer', 'Expected', 'Predicted', 'Score', 'Result']}>
                  {evaluation.cases.map((c: any) => (
                    <tr key={c.case_id} className="hover:bg-ink-50">
                      <td className="table-cell text-xs text-ink-600">{c.case_type.replace(/_/g, ' ')}</td>
                      <td className="table-cell text-xs font-medium text-ink-800">{c.customer_name}</td>
                      <td className="table-cell"><span className="chip border-ink-300 bg-ink-100 px-1.5 py-0.5 text-[10px]">{c.expected_priority}</span></td>
                      <td className="table-cell"><span className={`chip px-1.5 py-0.5 text-[10px] ${
                        c.predicted_priority === 'HIGH' ? 'border-red-300 bg-red-50 text-red-700'
                        : c.predicted_priority === 'MEDIUM' ? 'border-amber-300 bg-amber-50 text-amber-800'
                        : 'border-emerald-300 bg-emerald-50 text-emerald-800'
                      }`}>{c.predicted_priority}</span></td>
                      <td className="table-cell font-mono text-xs">{c.score.toFixed(1)}</td>
                      <td className="table-cell">
                        <span className={`text-xs font-semibold ${c.correct ? 'text-emerald-700' : c.within_one_band ? 'text-amber-700' : 'text-red-700'}`}>
                          {c.correct ? '✓ correct' : c.within_one_band ? '~ adjacent' : '✕ miss'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </Table>
              </div>
            </div>

            <p className="rounded-md border border-ink-200 bg-ink-50 p-3 text-[11px] leading-relaxed text-ink-600">
              These figures are measured output, not targets. Ground truth is the archetype the synthetic generator used to
              build each account, so exact-match accuracy penalises the engine for a defensible one-band difference. Read
              <strong> adjacent accuracy</strong> for tolerance and <strong>escalation failure rate</strong> for the risk that matters
              commercially — a HIGH account scored LOW.
            </p>
          </div>
        )}
      </Card>

      {/* ---------------- portfolio analytics ---------------- */}
      <div className="grid gap-6 xl:grid-cols-3">
        <Card title="Action distribution" subtitle="What the engine recommends across the book">
          <BarList data={dashboard.action_distribution} color="#0f766e" />
        </Card>
        <Card title="Issue distribution" subtitle="Open support tickets by severity">
          <BarList data={dashboard.issue_distribution} color="#dc2626" />
        </Card>
        <Card title="Priority distribution" subtitle="Accounts per band">
          <BarList data={dashboard.priority_distribution} color="#1b2130" />
        </Card>
      </div>

      <Card title="Signal weighting model" subtitle="Transparent, deterministic weights — the total is always 100 points">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>{['Signal', 'Weight', 'Source data', 'What it measures'].map((h) => (
                <th key={h} className="table-head px-3 py-2 whitespace-nowrap">{h}</th>
              ))}</tr>
            </thead>
            <tbody>
              {[
                ['Sales & revenue momentum', 22, 'sales', '30-day revenue and order count versus the prior 30 days'],
                ['Product usage trend', 24, 'usage_records', '14-day average daily active users versus the prior 14 days'],
                ['Support issue pressure', 20, 'support_tickets', 'Open ticket count weighted by severity and oldest age'],
                ['Engagement recency', 12, 'sales + usage_records', 'Days since the last sale and the last observed usage'],
                ['Revenue materiality', 12, 'sales + customers', 'Share of book revenue and contracted account value'],
                ['Account narrative risk', 10, 'business_notes', 'Rule-scanned risk language in notes and call records'],
              ].map(([signal, weight, source, what]) => (
                <tr key={String(signal)} className="hover:bg-ink-50">
                  <td className="table-cell text-xs font-semibold text-ink-800">{signal}</td>
                  <td className="table-cell font-mono text-xs font-semibold">{weight}</td>
                  <td className="table-cell mono text-ink-600">{source}</td>
                  <td className="table-cell text-xs text-ink-600">{what}</td>
                </tr>
              ))}
              <tr className="bg-ink-50">
                <td className="table-cell text-xs font-bold text-ink-900">Total</td>
                <td className="table-cell font-mono text-xs font-bold">100</td>
                <td className="table-cell" />
                <td className="table-cell text-xs text-ink-500">
                  Scaled over the signals that are actually measurable; confidence falls when signals are missing
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card>

      {health && (
        <Card title="Runtime configuration" subtitle="What is actually executing in this environment">
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            {[
              ['database', health.database],
              ['embedding backend', health.embedding_backend],
              ['vector backend', health.vector_backend],
              ['llm enabled', String(health.llm_enabled)],
              ['engine mode', health.engine_mode],
              ['reference date', health.reference_date],
            ].map(([k, v]: any) => (
              <div key={k}>
                <dt className="kv-label">{k}</dt>
                <dd className="mono mt-0.5 font-semibold text-ink-800">{String(v)}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 text-[11px] leading-relaxed text-ink-500">
            {health.llm_enabled
              ? 'A remote LLM is configured. It is used only to phrase explanations and answers from values the analytics layer already computed; it never produces a metric, a priority or a citation.'
              : 'No LLM key is configured, so the application is running its deterministic template engine. Priority, reasons, evidence and actions are identical — only the sentence phrasing changes. Set LLM_API_KEY to enable LLM phrasing.'}
          </p>
        </Card>
      )}
    </div>
  )
}
