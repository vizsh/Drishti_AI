import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, Hand, Radar, X } from 'lucide-react'
import { useLive } from '../state/LiveContext'
import { useHallScope } from '../state/useHallScope'
import { Badge } from './Badge'
import { shortAlertSummary } from '../lib/shortSummary'
import { playCriticalAlert, playWatchAlert } from '../lib/audio'
import type { AlertItem } from '../types'

const AUTO_DISMISS_MS = 7000
const MAX_VISIBLE = 4

// Same three-tone system as everywhere else — critical for a real alert,
// watch for a calibration-issue signal, neutral for a gesture note.
const KIND_STYLE: Record<AlertItem['kind'], { icon: typeof AlertTriangle; color: string; label: string }> = {
  alert: { icon: AlertTriangle, color: '#ff5a36', label: 'Alert' },
  gesture: { icon: Hand, color: '#8b8578', label: 'Gesture' },
  calibration_warning: { icon: Radar, color: '#ffb648', label: 'Calibration' },
}

// Real-time toast layer, mounted once in AppLayout so it persists across
// every route — a new alert should be noticeable regardless of what screen
// the invigilator is currently looking at, not just appended to a feed
// they may not be viewing.
export function ToastLayer() {
  const { alerts } = useLive()
  const { isSeatInScope } = useHallScope()
  const navigate = useNavigate()
  const [toasts, setToasts] = useState<AlertItem[]>([])
  const seenIds = useRef<Set<string> | null>(null)

  useEffect(() => {
    // First render after mount: just record what's already there, don't
    // toast the whole backlog of alerts that arrived before this mounted.
    if (seenIds.current === null) {
      seenIds.current = new Set(alerts.map((a) => a.id))
      return
    }
    const fresh = alerts.filter((a) => !seenIds.current!.has(a.id) && isSeatInScope(a.seatId))
    if (fresh.length === 0) return
    fresh.forEach((a) => seenIds.current!.add(a.id))
    setToasts((prev) => [...fresh, ...prev].slice(0, MAX_VISIBLE))
    fresh.forEach((a) => {
      setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== a.id)), AUTO_DISMISS_MS)
    })
    // Audio alerts for walking invigilators (frontend analysis §2)
    const hasCritical = fresh.some((a) => a.kind === 'alert')
    const hasWatch = fresh.some((a) => a.kind === 'gesture' || a.kind === 'calibration_warning')
    if (hasCritical) playCriticalAlert()
    else if (hasWatch) playWatchAlert()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alerts])

  function dismiss(id: string) {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }

  return (
    <div className="fixed top-5 right-5 z-[100] flex flex-col gap-2 w-80 pointer-events-none">
      <AnimatePresence initial={false}>
        {toasts.map((t) => {
          const style = KIND_STYLE[t.kind]
          const Icon = style.icon
          return (
            <motion.div
              key={t.id}
              layout
              initial={{ opacity: 0, x: 40 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 40 }}
              className="rounded-xl border p-3 pointer-events-auto cursor-pointer shadow-lg"
              style={{ borderColor: `${style.color}50`, background: '#0d0d11ee', backdropFilter: 'blur(8px)' }}
              onClick={() => {
                navigate(`/seat/${t.seatId}`)
                dismiss(t.id)
              }}
            >
              <div className="flex items-start gap-2.5">
                <Icon size={16} color={style.color} className="shrink-0 mt-0.5" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-xs font-bold">{t.seatId.toUpperCase()}</span>
                    <Badge tone={t.kind === 'alert' ? 'critical' : t.kind === 'calibration_warning' ? 'watch' : 'neutral'}>{style.label}</Badge>
                  </div>
                  <p className="text-[11px] text-white/70 leading-snug line-clamp-2">{shortAlertSummary(t.explanation)}</p>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    dismiss(t.id)
                  }}
                  className="text-white/30 hover:text-white/60 shrink-0"
                >
                  <X size={13} />
                </button>
              </div>
            </motion.div>
          )
        })}
      </AnimatePresence>
    </div>
  )
}
