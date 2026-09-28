import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { money } from '../lib/format'
import DecisionCard from '../components/DecisionCard'
import { Card, ConfidenceMeter, EmptyState, PriorityChip, ScoreBar, StatusChip } from '../components/ui'

/**
 * Ask DeciTrace — the business decision interface.
 *
 * This is deliberately NOT a chat clone. A question is routed into a named
 * analytics workflow, and the result is rendered as a structured decision
 * brief: workflow trace, matched accounts with priority and score, the
 * recommended action, and the verified evidence behind it.
 */
export default function Ask() {
  const [question, setQuestion] = useState('')
  const [examples, setExamples] = useState<string[]>([])
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [history, setHistory] = useState<{ question: string; intent: string; latency: number }[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api.askExamples().then((d) => setExamples(d.examples ?? [])).catch(() => setExamples([]))
  }, [])

  async function submit(q?: string) {
    const text = (q ?? question).trim()
    if (text.length < 2) return
    setLoading(true)
    setError(null)
    setQuestion(text)
    try {
      const data = await api.ask(text, undefined, 5)
      setResult(data)
      setHistory((h) => [{ question: text, intent: data.intent_label, latency: data.latency_ms }, ...h].slice(0, 6))
    } catch (e: any) {
      setError(e.message)
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-bold tracking-tight text-ink-900">Ask DeciTrace</h1>
        <p className="mt-1 max-w-3xl text-xs leading-relaxed text-ink-500">
          Ask an operational question in plain language. DeciTrace routes it to a concrete analytics workflow, executes
          deterministic business signals against the database, retrieves supporting evidence, and returns a prioritised
          decision brief — not a conversational reply.
        </p>
      </div>

      <Card title="Decision query" subtitle="The answer is assembled from computed metrics and verified records">
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            ref={inputRef}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !loading) submit()
            }}
            placeholder="Which customers should the sales team prioritize today and why?"
            className="min-w-0 flex-1 rounded-md border border-ink-200 px-3.5 py-2.5 text-sm outline-none focus:border-ink-400"
            disabled={loading}
          />
          <button className="btn-primary shrink-0" onClick={() => submit()} disabled={loading || question.trim().length < 2}>
            {loading ? 'Running workflow…' : 'Run decision workflow'}
          </button>
        </div>

        {examples.length > 0 && (
          <div className="mt-3">
            <div className="kv-label mb-1.5">Example questions</div>
            <div className="flex flex-wrap gap-1.5">
              {examples.map((ex) => (
                <button
                  key={ex}
                  onClick={() => submit(ex)}
                  disabled={loading}
                  className="rounded-md border border-ink-200 bg-white px-2.5 py-1.5 text-[11px] font-medium text-ink-700 transition-colors hover:bg-ink-50 disabled:opacity-50"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}

        {history.length > 0 && (
          <div className="mt-4 border-t border-ink-100 pt-3">
            <div className="kv-label mb-1.5">Recent queries in this session</div>
            <ul className="space-y-1">
              {history.map((h, i) => (
                <li key={i} className="flex flex-wrap items-center gap-2 text-[11px] text-ink-500">
                  <span className="mono">{h.intent}</span>
                  <span className="text-ink-300">·</span>
                  <span className="truncate">{h.question}</span>
                  <span className="ml-auto mono text-ink-400">{h.latency.toFixed(0)} ms</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      {error && (
        <div className="card border-red-200 bg-red-50 p-4">
          <div className="text-sm font-semibold text-red-800">Workflow could not complete</div>
          <div className="mt-1 text-xs text-red-700">{error}</div>
        </div>
      )}

      {loading && (
        <Card>
          <div className="space-y-3" role="status">
            <div className="text-xs font-medium text-ink-500">Executing workflow against the business database…</div>
            {['Parsing question', 'Applying deterministic signals', 'Retrieving and verifying evidence', 'Composing decision brief'].map((s, i) => (
              <div key={s} className="flex items-center gap-3">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-ink-100 text-[10px] font-bold text-ink-500">{i + 1}</span>
                <span className="text-xs text-ink-600">{s}</span>
                <div className="ml-auto h-1.5 w-32 animate-pulse rounded bg-ink-100" />
              </div>
            ))}
          </div>
        </Card>
      )}

      {result && !loading && (
        <>
          <Card
            title="Workflow executed"
            subtitle={result.intent_label}
            action={<span className="mono text-[11px] text-ink-500">{result.intent} · {result.latency_ms.toFixed(0)} ms</span>}
          >
            <ol className="flex flex-wrap gap-2">
              {result.workflow.map((step: string, i: number) => (
                <li key={step} className="flex items-center gap-2 rounded-md border border-ink-200 bg-ink-50/60 px-2.5 py-1.5">
                  <span className="flex h-4 w-4 items-center justify-center rounded-full bg-ink-900 text-[9px] font-bold text-white">{i + 1}</span>
                  <span className="text-[11px] font-medium text-ink-700">{step}</span>
                </li>
              ))}
            </ol>

            <div className="mt-4 rounded-md border border-ink-200 bg-white p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="chip border-ink-900 bg-ink-900 px-1.5 py-0.5 text-[10px] text-white">Answer</span>
                {result.llm_used ? (
                  <span className="chip border-violet-300 bg-violet-50 px-1.5 py-0.5 text-[10px] text-violet-700">LLM-phrased from computed values</span>
                ) : (
                  <span className="chip border-emerald-300 bg-emerald-50 px-1.5 py-0.5 text-[10px] text-emerald-700">Deterministic template</span>
                )}
              </div>
              <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-ink-800">{result.answer}</p>
            </div>

            {result.analytics && Object.keys(result.analytics).length > 0 && (
              <div className="mt-4">
                <div className="kv-label mb-2">Scope &amp; workflow telemetry</div>
                <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                  {Object.entries(result.analytics)
                    .filter(([, v]) => typeof v !== 'object')
                    .map(([k, v]: any) => (
                      <div key={k} className="rounded-md border border-ink-200 bg-ink-50/60 px-3 py-2">
                        <dt className="kv-label">{k.replace(/_/g, ' ')}</dt>
                        <dd className="mono mt-0.5 text-sm font-bold text-ink-900">
                          {typeof v === 'number' && k.includes('revenue') ? money(v) : String(v)}
                        </dd>
                      </div>
                    ))}
                </dl>
                {result.analytics.match_criteria && (
                  <div className="mt-3 rounded-md border border-ink-200 bg-white p-3">
                    <div className="kv-label mb-1">Filter applied</div>
                    <ul className="space-y-0.5">
                      {result.analytics.match_criteria.map((c: string) => (
                        <li key={c} className="mono text-[11px] text-ink-600">{c}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </Card>

          {result.results.length > 0 ? (
            <Card title={`Prioritised accounts (${result.results.length})`} subtitle="Matched by the workflow and scored by the decision engine">
              <ul className="divide-y divide-ink-100">
                {result.results.map((item: any) => (
                  <li key={item.decision_id} className="flex flex-wrap items-start gap-3 py-3">
                    <PriorityChip priority={item.priority} score={item.priority_score} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <Link to={`/customers/${item.customer_id}`} className="text-sm font-bold text-ink-900 hover:underline">
                          {item.customer_name}
                        </Link>
                        <span className="mono text-ink-400">{item.customer_id}</span>
                        <StatusChip status={item.status} />
                      </div>
                      <p className="mt-1 text-xs leading-relaxed text-ink-700">{item.reasons[0]}</p>
                      <div className="mt-1 flex flex-wrap gap-3 text-[10px] text-ink-500">
                        <span>action: {item.action_label}</span>
                        <span>{item.decision_id}</span>
                      </div>
                    </div>
                    <div className="w-36 shrink-0">
                      <ConfidenceMeter value={item.confidence} />
                      <div className="mt-2"><ScoreBar score={item.priority_score} priority={item.priority} /></div>
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          ) : (
            <EmptyState
              title="No account matched this workflow"
              hint="The query was understood and executed, but the deterministic filters returned nothing. Try a broader question."
            />
          )}

          {result.decisions?.length > 0 && (
            <section className="space-y-3">
              <h2 className="text-sm font-bold uppercase tracking-wider text-ink-500">
                Full decision brief{result.decisions.length > 1 ? `s (${result.decisions.length})` : ''}
              </h2>
              {result.decisions.map((d: any) => (
                <DecisionCard key={d.decision_id} decision={d} defaultOpen={result.decisions.length === 1} />
              ))}
            </section>
          )}

          {result.evidence?.length > 0 && (
            <Card title={`Evidence retrieved (${result.evidence.length})`} subtitle="Every record resolves to a row in the operational database">
              <ol className="space-y-2.5">
                {result.evidence.map((ev: any) => (
                  <li key={`${ev.source_table}-${ev.source_id}-${ev.rank}`} className="rounded-md border border-ink-200 bg-white p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-ink-900 text-[10px] font-bold text-white">{ev.rank}</span>
                      <span className="chip border-ink-200 bg-ink-50 px-1.5 py-0.5 text-[10px] text-ink-600">{ev.source_table}</span>
                      <span className="mono font-semibold">{ev.source_id}</span>
                      {ev.customer_id && <span className="mono text-ink-400">{ev.customer_id}</span>}
                      <span className="chip border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[9px] text-emerald-700">verified</span>
                    </div>
                    <div className="mt-1.5 text-xs font-semibold text-ink-800">{ev.title}</div>
                    <p className="mt-1 text-[11px] leading-relaxed text-ink-600">{ev.snippet}</p>
                  </li>
                ))}
              </ol>
            </Card>
          )}
        </>
      )}

      {!result && !loading && !error && (
        <EmptyState
          title="No workflow executed yet"
          hint="Pick an example question above, or type your own. DeciTrace will show the workflow it ran along with the computed metrics and the evidence behind every recommendation."
        />
      )}
    </div>
  )
}
