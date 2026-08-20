import { createContext, useContext, type ReactNode } from 'react'
import { useLiveSocket } from '../hooks/useLiveSocket'

type LiveContextValue = ReturnType<typeof useLiveSocket>

const LiveContext = createContext<LiveContextValue | null>(null)

export function LiveProvider({ children }: { children: ReactNode }) {
  // Single WebSocket connection for the whole app — every route reads from
  // this same context instead of each mounting its own useLiveSocket() and
  // opening a second connection.
  const value = useLiveSocket()
  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>
}

export function useLive(): LiveContextValue {
  const ctx = useContext(LiveContext)
  if (!ctx) throw new Error('useLive() must be used within <LiveProvider>')
  return ctx
}
