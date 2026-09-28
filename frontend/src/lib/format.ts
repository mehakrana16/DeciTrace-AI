export function money(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `$${Number(value).toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`
}

export function compactMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const abs = Math.abs(value)
  if (abs >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`
  if (abs >= 1_000) return `$${(value / 1_000).toFixed(1)}K`
  return `$${value.toFixed(0)}`
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${value > 0 ? '+' : ''}${Number(value).toFixed(digits)}%`
}

export function num(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return Number(value).toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function dateStr(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: '2-digit' })
}

export function dateTimeStr(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return d.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function relativeDays(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  const days = Math.round((Date.now() - d.getTime()) / 86_400_000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 30) return `${days} days ago`
  const months = Math.round(days / 30)
  return months === 1 ? '1 month ago' : `${months} months ago`
}

/** Colour tokens for the three priority bands — used consistently everywhere. */
export const PRIORITY_STYLE: Record<string, { chip: string; dot: string; bar: string; text: string }> = {
  HIGH: {
    chip: 'border-red-300 bg-red-50 text-red-700',
    dot: 'bg-red-600',
    bar: 'bg-red-600',
    text: 'text-red-700',
  },
  MEDIUM: {
    chip: 'border-amber-300 bg-amber-50 text-amber-800',
    dot: 'bg-amber-500',
    bar: 'bg-amber-500',
    text: 'text-amber-700',
  },
  LOW: {
    chip: 'border-emerald-300 bg-emerald-50 text-emerald-800',
    dot: 'bg-emerald-600',
    bar: 'bg-emerald-600',
    text: 'text-emerald-700',
  },
}

export const CHART_COLORS = [
  '#1b2130',
  '#c2410c',
  '#0f766e',
  '#7c3aed',
  '#b45309',
  '#0369a1',
  '#be123c',
  '#4d7c0f',
]

export function priorityStyle(priority: string | null | undefined) {
  return PRIORITY_STYLE[(priority || 'LOW').toUpperCase()] ?? PRIORITY_STYLE.LOW
}

export function signalColor(direction: string): string {
  if (direction === 'risk') return 'text-red-700'
  if (direction === 'positive') return 'text-emerald-700'
  return 'text-ink-500'
}
