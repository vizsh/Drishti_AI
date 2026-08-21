import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../state/AuthContext'

/** Phase 1: "cannot reach any dashboard route without logging in" — a real
 * route guard, not a UI that silently does nothing. Redirects to /login and
 * remembers where the user was headed so login sends them back there. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, sessionLoading } = useAuth()
  const location = useLocation()
  // While silently re-authenticating (cookie rehydration), hold rendering
  if (sessionLoading) return null
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return children
}
