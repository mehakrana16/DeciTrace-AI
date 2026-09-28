import { NavLink, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { api } from './lib/api'
import Dashboard from './pages/Dashboard'
import Customers from './pages/Customers'
import CustomerDetail from './pages/CustomerDetail'
import Decisions from './pages/Decisions'
import Evidence from './pages/Evidence'
import Analytics from './pages/Analytics'
import Ask from './pages/Ask'

const NAV = [
  { to: '/', label: 'Dashboard', end: true, icon: 'M3 12h4l2.5-6 3 12L15 9h6' },
  { to: '/customers', label: 'Customers', icon: 'M16 20v-1a4 4 0 0 0-8 0v1M12 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z' },
  { to: '/decisions', label: 'Decisions', icon: 'M9 12.5 11 15l4.5-5M5 4h14v16l-7-3-7 3Z' },
  { to: '/evidence', label: 'Evidence', icon: 'M4 5h16v5H4zM4 14h16v6H4zM8 7.5h.01M8 17h.01' },
  { to: '/analytics', label: 'Analytics & Evaluation', icon: 'M4 20V9M10 20V4M16 20v-7M22 20H2' },
  { to: '/ask', label: 'Ask DeciTrace', icon: 'M8 10h.01M12 10h.01M16 10h.01M21 12a9 9 0 1 1-3.6-7.2' },
]

function Icon({ path }: { path: string }) {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d={path} />
    </svg>
  )
}

function Shell() {
  const [health, setHealth] = useState<any>(null)
  const [navOpen, setNavOpen] = useState(false)
  const location = useLocation()

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null))
  }, [])

  useEffect(() => {
    setNavOpen(false)
  }, [location.pathname])

  const mode = health
    ? health.llm_enabled
      ? 'LLM-assisted'
      : 'Deterministic'
    : '—'

  return (
    <div className="flex min-h-screen flex-col bg-ink-50">
      <header className="sticky top-0 z-30 border-b border-ink-200 bg-white">
        <div className="mx-auto flex max-w-[1600px] items-center gap-4 px-4 py-3 sm:px-6">
          <button
            className="rounded-md border border-ink-200 p-2 lg:hidden"
            onClick={() => setNavOpen((v) => !v)}
            aria-label="Toggle navigation"
          >
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 7h16M4 12h16M4 17h16" />
            </svg>
          </button>

          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-ink-900">
              <svg viewBox="0 0 24 24" className="h-4 w-4 text-white" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M4 19V5M4 15l5-5 3.5 3.5L20 6" />
                <circle cx="20" cy="6" r="1.6" fill="currentColor" stroke="none" />
              </svg>
            </div>
            <div className="leading-tight">
              <div className="text-[15px] font-bold tracking-tight text-ink-900">DECITRACE AI</div>
              <div className="hidden text-[11px] text-ink-500 sm:block">Evidence-Grounded Business Decision Engine</div>
            </div>
          </div>

          <div className="ml-auto flex items-center gap-2">
            {health && (
              <span className="hidden items-center gap-1.5 rounded-md border border-ink-200 px-2 py-1 text-[11px] font-medium text-ink-600 md:inline-flex">
                <span className={`h-1.5 w-1.5 rounded-full ${health.llm_enabled ? 'bg-violet-500' : 'bg-emerald-500'}`} />
                Engine: {mode}
              </span>
            )}
            {health && (
              <span className="hidden items-center gap-1.5 rounded-md border border-ink-200 px-2 py-1 text-[11px] font-medium text-ink-600 lg:inline-flex">
                RAG: {health.vector_backend} · {health.embedding_backend}
              </span>
            )}
            <span className="inline-flex items-center gap-1.5 rounded-md border border-ink-200 px-2 py-1 text-[11px] font-medium text-ink-600">
              <span className={`h-1.5 w-1.5 rounded-full ${health ? 'bg-emerald-500' : 'bg-ink-300'}`} />
              {health ? 'API online' : 'API offline'}
            </span>
          </div>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-[1600px] flex-1 gap-6 px-4 py-6 sm:px-6">
        <nav className={`${navOpen ? 'block' : 'hidden'} absolute left-4 right-4 top-[68px] z-20 rounded-lg border border-ink-200 bg-white p-2 shadow-lg lg:static lg:block lg:w-60 lg:shrink-0 lg:border-0 lg:bg-transparent lg:p-0 lg:shadow-none`}>
          <ul className="space-y-1">
            {NAV.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.end as boolean | undefined}
                  className={({ isActive }) =>
                    `flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                      isActive ? 'bg-ink-900 text-white' : 'text-ink-700 hover:bg-ink-100'
                    }`
                  }
                >
                  <Icon path={item.icon} />
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>

          <div className="mt-4 hidden rounded-lg border border-ink-200 bg-white p-3 lg:block">
            <div className="card-title mb-2">Decision pipeline</div>
            <ol className="space-y-1.5 text-[11px] text-ink-600">
              {['Business data', 'Processing', 'Analytics', 'RAG evidence', 'Signal fusion', 'Decision engine', 'Priority + reason', 'Evidence trace', 'Human approval'].map((step, i) => (
                <li key={step} className="flex items-center gap-2">
                  <span className="flex h-4 w-4 items-center justify-center rounded-full bg-ink-100 text-[9px] font-bold text-ink-600">{i + 1}</span>
                  {step}
                </li>
              ))}
            </ol>
          </div>

          {health && (
            <div className="mt-4 hidden rounded-lg border border-ink-200 bg-white p-3 lg:block">
              <div className="card-title mb-2">Database</div>
              <dl className="space-y-1 text-[11px]">
                {Object.entries(health.rows).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-2">
                    <dt className="text-ink-500">{k.replace(/_/g, ' ')}</dt>
                    <dd className="font-mono font-medium text-ink-800">{String(v)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
        </nav>

        <main className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>

      <footer className="border-t border-ink-200 bg-white">
        <div className="mx-auto flex max-w-[1600px] flex-col gap-1 px-4 py-4 text-[11px] text-ink-500 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <span>
            DECITRACE AI · Evidence-Grounded Business Decision Engine · {health?.version ? `v${health.version}` : ''}
          </span>
          <span>
            PS-04 AI Decision Engine for Business Data · synthetic dataset · all decisions require human approval
          </span>
        </div>
      </footer>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Dashboard />} />
        <Route path="customers" element={<Customers />} />
        <Route path="customers/:customerId" element={<CustomerDetail />} />
        <Route path="decisions" element={<Decisions />} />
        <Route path="evidence" element={<Evidence />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="ask" element={<Ask />} />
        <Route path="*" element={<div className="card card-pad text-sm text-ink-600">Page not found.</div>} />
      </Route>
    </Routes>
  )
}
