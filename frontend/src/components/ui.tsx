import { ReactNode } from 'react'
import { money, priorityStyle } from '../lib/format'

/* ------------------------------------------------------------------ states */
export function LoadingState({ label = 'Loading', rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div className="space-y-3" role="status" aria-live="polite">
      <div className="text-xs font-medium text-ink-500">{label}…</div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="card animate-pulse p-5">
          <div className="h-3 w-1/3 rounded bg-ink-100" />
          <div className="mt-3 h-3 w-2/3 rounded bg-ink-100" />
          <div className="mt-3 h-3 w-1/2 rounded bg-ink-100" />
        </div>
      ))}
    </div>
  )
}

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="card flex flex-col items-center justify-center px-6 py-12 text-center">
      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-ink-100">
        <svg viewBox="0 0 24 24" className="h-5 w-5 text-ink-400" fill="none" stroke="currentColor" strokeWidth="1.7">
          <path d="M4 6h16v12H4zM4 10h16" />
        </svg>
      </div>
      <div className="text-sm font-semibold text-ink-800">{title}</div>
      {hint && <div className="mt-1 max-w-md text-xs text-ink-500">{hint}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="card border-red-200 bg-red-50 p-5">
      <div className="text-sm font-semibold text-red-800">Request failed</div>
      <div className="mt-1 text-xs text-red-700">{message}</div>
      {onRetry && (
        <button className="btn-reject mt-3" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------- atoms */
export function Card({ title, subtitle, action, children, className = '' }: {
  title?: string
  subtitle?: string
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-3 border-b border-ink-100 px-5 py-3.5">
          <div>
            {title && <h2 className="card-title">{title}</h2>}
            {subtitle && <p className="mt-1 text-xs text-ink-500">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className="card-pad">{children}</div>
    </section>
  )
}

export function PriorityChip({ priority, score, size = 'md' }: { priority: string; score?: number; size?: 'sm' | 'md' }) {
  const s = priorityStyle(priority)
  const pad = size === 'sm' ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-0.5 text-xs'
  return (
    <span className={`chip ${s.chip} ${pad}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {priority}
      {score !== undefined && score !== null && <span className="font-mono opacity-70">{score.toFixed(1)}</span>}
    </span>
  )
}

export function StatusChip({ status }: { status: string }) {
  const map: Record<string, string> = {
    pending: 'border-ink-300 bg-ink-100 text-ink-700',
    approved: 'border-emerald-300 bg-emerald-50 text-emerald-800',
    rejected: 'border-red-300 bg-red-50 text-red-700',
    open: 'border-red-300 bg-red-50 text-red-700',
    in_progress: 'border-amber-300 bg-amber-50 text-amber-800',
    resolved: 'border-emerald-300 bg-emerald-50 text-emerald-800',
    active: 'border-emerald-300 bg-emerald-50 text-emerald-800',
    at_risk: 'border-red-300 bg-red-50 text-red-700',
    onboarding: 'border-sky-300 bg-sky-50 text-sky-800',
  }
  return (
    <span className={`chip ${map[status] ?? 'border-ink-300 bg-ink-100 text-ink-700'} px-1.5 py-0.5 text-[10px]`}>
      {status.replace(/_/g, ' ')}
    </span>
  )
}

export function KpiCard({ kpi }: { kpi: { label: string; value: any; unit?: string; delta_pct?: number | null; hint?: string } }) {
  const isMoney = kpi.unit === 'USD'
  const rendered = isMoney ? money(Number(kpi.value)) : kpi.value
  return (
    <div className="card p-4">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-500">{kpi.label}</div>
      <div className="mt-1.5 flex items-baseline gap-1.5">
        <span className="text-2xl font-bold tabular-nums tracking-tight text-ink-900">{rendered}</span>
        {kpi.unit && kpi.unit !== 'USD' && <span className="text-xs font-medium text-ink-400">{kpi.unit}</span>}
      </div>
      <div className="mt-1 flex items-center gap-2">
        {kpi.delta_pct !== undefined && kpi.delta_pct !== null && (
          <span className={`text-xs font-semibold ${kpi.delta_pct < 0 ? 'text-red-600' : 'text-emerald-600'}`}>
            {kpi.delta_pct > 0 ? '▲' : '▼'} {Math.abs(kpi.delta_pct).toFixed(1)}%
          </span>
        )}
        {kpi.hint && <span className="truncate text-[11px] text-ink-500">{kpi.hint}</span>}
      </div>
    </div>
  )
}

export function ScoreBar({ score, priority }: { score: number; priority: string }) {
  const s = priorityStyle(priority)
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-100">
      <div className={`h-full rounded-full ${s.bar}`} style={{ width: `${Math.min(100, score)}%` }} />
    </div>
  )
}

export function ConfidenceMeter({ value, label }: { value: number; label?: string }) {
  const pctv = Math.round(value * 100)
  return (
    <div className="flex items-center gap-2">
      <div className="flex h-1.5 w-16 overflow-hidden rounded-full bg-ink-100">
        <div className="h-full bg-ink-700" style={{ width: `${pctv}%` }} />
      </div>
      <span className="text-[11px] font-medium tabular-nums text-ink-600">
        {pctv}%{label ? ` ${label}` : ''}
      </span>
    </div>
  )
}

export function SignalRow({ signal }: { signal: any }) {
  const max = signal.weight_max || 1
  const ratio = Math.max(0, Math.min(1, (signal.points || 0) / max))
  const color = signal.direction === 'risk' ? 'bg-red-600' : signal.direction === 'positive' ? 'bg-emerald-600' : 'bg-ink-300'
  const textColor = signal.direction === 'risk' ? 'text-red-700' : signal.direction === 'positive' ? 'text-emerald-700' : 'text-ink-500'
  return (
    <div className="border-b border-ink-100 py-2.5 last:border-0">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className={`text-xs font-semibold ${textColor}`}>{signal.label}</span>
          {!signal.has_data && <span className="chip border-ink-200 bg-ink-50 px-1.5 py-0.5 text-[9px] text-ink-500">no data</span>}
        </div>
        <span className="shrink-0 font-mono text-[11px] font-semibold text-ink-700">
          {signal.points.toFixed(1)}/{signal.weight_max.toFixed(0)}
        </span>
      </div>
      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-ink-100">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${ratio * 100}%` }} />
      </div>
      <p className="mt-1.5 text-[11px] leading-relaxed text-ink-600">{signal.reason}</p>
    </div>
  )
}

/* ------------------------------------------------------------------ charts */
export function Donut({ data, size = 132, thickness = 18 }: { data: { label: string; value: number }[]; size?: number; thickness?: number }) {
  const total = data.reduce((sum, d) => sum + d.value, 0)
  const radius = (size - thickness) / 2
  const circumference = 2 * Math.PI * radius
  const colors: Record<string, string> = { HIGH: '#dc2626', MEDIUM: '#f59e0b', LOW: '#059669' }
  let offset = 0

  if (total === 0) return <div className="py-8 text-center text-xs text-ink-400">No data</div>

  return (
    <div className="flex items-center gap-5">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Priority distribution">
        <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
          {data.map((d, i) => {
            const len = (d.value / total) * circumference
            const el = (
              <circle
                key={d.label}
                cx={size / 2}
                cy={size / 2}
                r={radius}
                fill="none"
                stroke={colors[d.label] ?? ['#1b2130', '#c2410c', '#0f766e', '#7c3aed'][i % 4]}
                strokeWidth={thickness}
                strokeDasharray={`${len} ${circumference - len}`}
                strokeDashoffset={-offset}
              />
            )
            offset += len
            return el
          })}
        </g>
        <text x="50%" y="47%" textAnchor="middle" className="fill-ink-900 text-[20px] font-bold">{total}</text>
        <text x="50%" y="62%" textAnchor="middle" className="fill-ink-400 text-[10px] font-semibold uppercase tracking-wider">accounts</text>
      </svg>
      <ul className="space-y-2">
        {data.map((d) => (
          <li key={d.label} className="flex items-center gap-2 text-xs">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: colors[d.label] ?? '#1b2130' }} />
            <span className="w-16 font-medium text-ink-700">{d.label}</span>
            <span className="font-mono font-semibold tabular-nums text-ink-900">{d.value}</span>
            <span className="text-ink-400">{total ? `${Math.round((d.value / total) * 100)}%` : ''}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function BarList({ data, color = '#1b2130', money_ = false }: { data: { label: string; value: number }[]; color?: string; money_?: boolean }) {
  const max = Math.max(1, ...data.map((d) => d.value))
  if (!data.length) return <div className="py-6 text-center text-xs text-ink-400">No data</div>
  return (
    <ul className="space-y-2.5">
      {data.map((d) => (
        <li key={d.label}>
          <div className="flex items-center justify-between gap-3 text-xs">
            <span className="truncate font-medium text-ink-700">{d.label}</span>
            <span className="shrink-0 font-mono font-semibold tabular-nums text-ink-900">
              {money_ ? money(d.value) : d.value}
            </span>
          </div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-ink-100">
            <div className="h-full rounded-full" style={{ width: `${(d.value / max) * 100}%`, background: color }} />
          </div>
        </li>
      ))}
    </ul>
  )
}

export function LineChart({ series, height = 180, color = '#1b2130', valueFormat = (v: number) => `${(v / 1000).toFixed(0)}K` }: {
  series: { date: string; value: number }[]
  height?: number
  color?: string
  valueFormat?: (v: number) => string
}) {
  if (!series || series.length < 2) {
    return <div className="flex items-center justify-center py-10 text-xs text-ink-400" style={{ height }}>Not enough data points</div>
  }
  const width = 720
  const padL = 48
  const padR = 12
  const padT = 12
  const padB = 26
  const values = series.map((s) => s.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const innerW = width - padL - padR
  const innerH = height - padT - padB
  const x = (i: number) => padL + (i / (series.length - 1)) * innerW
  const y = (v: number) => padT + innerH - ((v - min) / span) * innerH

  const line = series.map((s, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(s.value).toFixed(1)}`).join(' ')
  const area = `${line} L${x(series.length - 1).toFixed(1)},${(padT + innerH).toFixed(1)} L${padL},${(padT + innerH).toFixed(1)} Z`
  const ticks = [min, min + span / 2, max]
  const labelEvery = Math.max(1, Math.floor(series.length / 6))

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ height }} role="img" aria-label="Trend chart">
      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={padL} x2={width - padR} y1={y(t)} y2={y(t)} stroke="#eceef2" strokeWidth="1" />
          <text x={padL - 6} y={y(t) + 3} textAnchor="end" className="fill-ink-400 text-[9px]">{valueFormat(t)}</text>
        </g>
      ))}
      <path d={area} fill={color} opacity="0.07" />
      <path d={line} fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round" />
      {series.map((s, i) =>
        i % labelEvery === 0 ? (
          <text key={s.date} x={x(i)} y={height - 8} textAnchor="middle" className="fill-ink-400 text-[9px]">
            {new Date(s.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
          </text>
        ) : null,
      )}
    </svg>
  )
}

export function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr>
            {head.map((h) => (
              <th key={h} className="table-head px-3 py-2 whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}
