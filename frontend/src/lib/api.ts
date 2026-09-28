/**
 * Typed-ish API client. Every call hits a real backend endpoint — there are no
 * mocked responses anywhere in this application.
 */
const BASE: string = (import.meta.env.VITE_API_URL as string | undefined) ?? ''

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
  } catch (error) {
    throw new ApiError(
      'Cannot reach the DeciTrace API. Is the backend running on port 8000?',
      0,
    )
  }

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: any) => d.msg).join('; ')
      else if (body.detail) detail = JSON.stringify(body.detail)
    } catch {
      /* keep the default message */
    }
    throw new ApiError(detail, response.status)
  }
  return (await response.json()) as T
}

export const api = {
  health: () => request<any>('/api/health'),
  dashboard: () => request<any>('/api/dashboard'),
  customers: (query = '') => request<any[]>(`/api/customers${query}`),
  customer: (id: string) => request<any>(`/api/customers/${encodeURIComponent(id)}`),
  decisions: (query = '') => request<any[]>(`/api/decisions${query}`),
  decision: (id: string) => request<any>(`/api/decisions/${encodeURIComponent(id)}`),
  evidence: (decisionId: string) =>
    request<any[]>(`/api/evidence/${encodeURIComponent(decisionId)}`),
  ask: (question: string, customerId?: string, limit = 5) =>
    request<any>('/api/ask', {
      method: 'POST',
      body: JSON.stringify({ question, customer_id: customerId ?? null, limit }),
    }),
  askExamples: () => request<any>('/api/ask/examples'),
  approve: (id: string, note = '') =>
    request<any>(`/api/decisions/${encodeURIComponent(id)}/approve`, {
      method: 'POST',
      body: JSON.stringify({ actor: 'sales.manager@example.com', note }),
    }),
  reject: (id: string, note = '') =>
    request<any>(`/api/decisions/${encodeURIComponent(id)}/reject`, {
      method: 'POST',
      body: JSON.stringify({ actor: 'sales.manager@example.com', note }),
    }),
  evaluate: (caseTypes?: string[]) =>
    request<any>('/api/evaluate', {
      method: 'POST',
      body: JSON.stringify({ case_types: caseTypes ?? null, include_llm: false }),
    }),
  evaluation: () => request<any>('/api/evaluation'),
  regenerate: () =>
    request<any>('/api/admin/regenerate-decisions', { method: 'POST' }),
}
