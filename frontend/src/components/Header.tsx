import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { Radar } from 'lucide-react'
import { STATUS_COLOR } from '../lib/colors'

export function Header({ connected, cameraOnline }: { connected: boolean; cameraOnline: boolean }) {
  const clock = useSessionClock()
  return (
    <header className="flex items-center justify-between py-6">
      <div className="flex items-center gap-4">
        <motion.div
          className="w-12 h-12 rounded-2xl flex items-center justify-center bg-white/10"
          animate={{ rotate: [0, 6, -6, 0] }}
          transition={{ duration: 6, repeat: Infinity, ease: 'easeInOut' }}
        >
          <Radar size={22} className="text-ink" strokeWidth={2.4} />
        </motion.div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight leading-none">
            KINESIS<span className="text-white/40">.</span>
          </h1>
          <p className="text-[11px] mono uppercase tracking-[0.2em] text-white/40 mt-1">exam behaviour monitor</p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <div className="text-right hidden sm:block mr-2">
          <div className="text-[10px] mono uppercase tracking-wider text-white/35">session</div>
          <div className="text-sm mono font-semibold">{clock}</div>
        </div>
        <StatusPill label={cameraOnline ? 'camera online' : 'camera degraded'} ok={cameraOnline} />
        <StatusPill label={connected ? 'live' : 'connecting'} ok={connected} pulse />
      </div>
    </header>
  )
}

// A more prominent connection-status indicator than the small inline
// Badge (components/Badge.tsx) — deliberately bigger, with a live-pulse
// dot, since it's the header's own persistent system-health readout.
function StatusPill({ label, ok, pulse }: { label: string; ok: boolean; pulse?: boolean }) {
  const color = ok ? STATUS_COLOR.calm : STATUS_COLOR.critical
  return (
    <div
      className="flex items-center gap-2 px-3.5 py-2 rounded-full border text-[11px] mono uppercase tracking-wide"
      style={{ borderColor: `${color}40`, background: `${color}0f`, color }}
    >
      <span className="relative flex h-1.5 w-1.5">
        {pulse && ok && <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: color }} />}
        <span className="relative inline-flex rounded-full h-1.5 w-1.5" style={{ background: color }} />
      </span>
      {label}
    </div>
  )
}

function useSessionClock(): string {
  const startRef = useRef(Date.now())
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  const secs = Math.floor((now - startRef.current) / 1000)
  const h = String(Math.floor(secs / 3600)).padStart(2, '0')
  const m = String(Math.floor((secs % 3600) / 60)).padStart(2, '0')
  const s = String(secs % 60).padStart(2, '0')
  return `${h}:${m}:${s}`
}
