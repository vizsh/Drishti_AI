import { useEffect } from 'react'
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion'

function AnimatedNumber({ value, decimals = 0 }: { value: number; decimals?: number }) {
  const mv = useMotionValue(value)
  const spring = useSpring(mv, { stiffness: 90, damping: 20 })
  const display = useTransform(spring, (v) => v.toFixed(decimals))
  useEffect(() => { mv.set(value) }, [value, mv])
  return <motion.span>{display}</motion.span>
}

interface Props {
  seatsMonitored: number
  calibrated: number
  alerts: number
  avgRisk: number
}

export function StatStrip({ seatsMonitored, calibrated, alerts, avgRisk }: Props) {
  const items = [
    { label: 'seats monitored', value: seatsMonitored, decimals: 0 },
    { label: 'calibrated', value: calibrated, decimals: 0 },
    // Amber only once there's actually something to watch — a zero-alert
    // count shouldn't draw the eye the same way a nonzero one should.
    { label: 'alerts (session)', value: alerts, decimals: 0, accent: alerts > 0 },
    { label: 'avg risk', value: avgRisk, decimals: 2 },
  ]
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
      {items.map((it, i) => (
        <motion.div
          key={it.label}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.05 }}
          className="rounded-2xl px-5 py-4 border border-white/8 bg-white/3"
        >
          <div className="text-[10px] mono uppercase tracking-widest text-white/35 mb-1.5">{it.label}</div>
          <div className={`text-3xl font-bold tabular-nums ${it.accent ? 'text-watch' : 'text-ink'}`}>
            <AnimatedNumber value={it.value} decimals={it.decimals} />
          </div>
        </motion.div>
      ))}
    </div>
  )
}
