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
  login: (email: string, password: string) => { ok: boolean; error?: string }
  logout: () => void
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

  function login(email: string, password: string) {
    const account = DEMO_ACCOUNTS.find((a) => a.email.toLowerCase() === email.toLowerCase())
    if (!account || account.password !== password) {
      return { ok: false, error: 'Incorrect email or password.' }
    }
    setUser(account)
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ email: account.email }))
    return { ok: true }
  }

  function logout() {
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
