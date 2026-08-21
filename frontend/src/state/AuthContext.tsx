import { createContext, useContext, useState, useEffect, useRef, useCallback, type ReactNode } from 'react'

export type Role = 'controller' | 'invigilator'

export interface DemoAccount {
  email: string
  password: string
  name: string
  role: Role
  hall: string | null // null = Controller, sees every hall
  initials: string
}

// Dummy auth (Phase 1 spec: "dummy auth is fine, but implement it as an
// actual route guard"). Real deployment swaps this for a real identity
// provider without changing how the rest of the app consumes useAuth().
export const DEMO_ACCOUNTS: DemoAccount[] = [
  { email: 'controller@kinesis.ai', password: 'demo1234', name: 'M. Chen', role: 'controller', hall: null, initials: 'MC' },
  { email: 'invigilator.a@kinesis.ai', password: 'demo1234', name: 'R. Fernandes', role: 'invigilator', hall: 'Hall A', initials: 'RF' },
  { email: 'invigilator.b@kinesis.ai', password: 'demo1234', name: 'S. Okafor', role: 'invigilator', hall: 'Hall B', initials: 'SO' },
]

const STORAGE_KEY = 'kinesis_auth_session'

interface AuthContextValue {
  user: DemoAccount | null
  /** True while we're silently re-authenticating a stored session on mount */
  sessionLoading: boolean
  login: (email: string, password: string) => Promise<{ ok: boolean; error?: string }>
  logout: () => Promise<void>
  /** Fetch wrapper that auto-intercepts 401 responses and triggers logout */
  authFetch: typeof fetch
}

const AuthContext = createContext<AuthContextValue | null>(null)

function loadStoredCredentials(): { email: string; password: string } | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (parsed.email && parsed.password) return { email: parsed.email, password: parsed.password }
    // Old format without password — can't rehydrate, force re-login
    return null
  } catch {
    return null
  }
}

function storedToAccount(email: string): DemoAccount | null {
  return DEMO_ACCOUNTS.find((a) => a.email === email) ?? null
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const stored = loadStoredCredentials()
  const [user, setUser] = useState<DemoAccount | null>(stored ? storedToAccount(stored.email) : null)
  const [sessionLoading, setSessionLoading] = useState(!!stored)
  const loggingOut = useRef(false)

  // On mount: if we have stored credentials, silently re-authenticate with the
  // backend to re-establish the HttpOnly cookie. If it fails, clear everything.
  useEffect(() => {
    if (!stored) return
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch('/api/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: stored.email, password: stored.password }),
        })
        if (!res.ok) {
          // Stored credentials are invalid — force re-login
          if (!cancelled) {
            setUser(null)
            localStorage.removeItem(STORAGE_KEY)
          }
        }
      } catch {
        // Backend not reachable — keep the UI user but cookie may fail later
      } finally {
        if (!cancelled) setSessionLoading(false)
      }
    })()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // run once on mount

  const forceLogout = useCallback(() => {
    if (loggingOut.current) return
    loggingOut.current = true
    setUser(null)
    localStorage.removeItem(STORAGE_KEY)
    // Best-effort server-side logout (cookie may already be invalid)
    fetch('/api/logout', { method: 'POST' }).catch(() => {})
    loggingOut.current = false
  }, [])

  async function login(email: string, password: string) {
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      if (!res.ok) {
        const errData = await res.json()
        return { ok: false, error: errData.detail || 'Incorrect email or password.' }
      }
      const data = await res.json()
      setUser(data.user)
      // Store both email AND password so we can rehydrate the cookie on next page load
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ email: data.user.email, password }))
      return { ok: true }
    } catch {
      return { ok: false, error: 'Failed to connect to authentication server.' }
    }
  }

  async function logout() {
    try {
      await fetch('/api/logout', { method: 'POST' })
    } catch {
      // ignore logout connection error
    }
    setUser(null)
    localStorage.removeItem(STORAGE_KEY)
  }

  /** Wrapper around fetch() that intercepts 401 responses and triggers logout */
  const authFetch: typeof fetch = useCallback(async (input: RequestInfo | URL, init?: RequestInit) => {
    const res = await fetch(input, init)
    if (res.status === 401) {
      forceLogout()
    }
    return res
  }, [forceLogout])

  return (
    <AuthContext.Provider value={{ user, sessionLoading, login, logout, authFetch }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth() must be used within <AuthProvider>')
  return ctx
}
