const API = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

export function token(): string {
  return localStorage.getItem('delta_token') || ''
}

export function setToken(value: string): void {
  if (value) localStorage.setItem('delta_token', value)
  else localStorage.removeItem('delta_token')
}

export async function api(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers || {})
  headers.set('Accept', 'application/json')

  if (token()) headers.set('Authorization', `Bearer ${token()}`)

  if (
    init.body &&
    !(init.body instanceof FormData) &&
    !(init.body instanceof URLSearchParams) &&
    !headers.has('Content-Type')
  ) {
    headers.set('Content-Type', 'application/json')
  }

  if (init.body instanceof URLSearchParams && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/x-www-form-urlencoded')
  }

  let response: Response
  try {
    response = await fetch(`${API}${path}`, { ...init, headers })
  } catch {
    throw new Error(`Cannot connect to backend at ${API}. Start the FastAPI server and check VITE_API_URL.`)
  }

  const data = await response.json().catch(() => ({ detail: response.statusText }))
  if (!response.ok) {
    const detail = typeof data?.detail === 'string'
      ? data.detail
      : JSON.stringify(data?.detail || data?.error || `HTTP ${response.status}`)
    throw new Error(detail)
  }
  return data
}
