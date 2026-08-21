import { createContext, useContext, useState, type ReactNode } from 'react'

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
  login: (email: string, password: string) => Promise<{ ok: boolean; error?: string }>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

function loadStoredUser(): DemoAccount | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const email = JSON.parse(raw).email
    return DEMO_ACCOUNTS.find((a) => a.email === email) ?? null
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<DemoAccount | null>(loadStoredUser)

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
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ email: data.user.email }))
      return { ok: true }
    } catch (e) {
      return { ok: false, error: 'Failed to connect to authentication server.' }
    }
  }

  async function logout() {
    try {
      await fetch('/api/logout', { method: 'POST' })
    } catch (e) {
      // ignore logout connection error
    }
    setUser(null)
    localStorage.removeItem(STORAGE_KEY)
  }

  return <AuthContext.Provider value={{ user, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth() must be used within <AuthProvider>')
  return ctx
}
