import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { UserRoundSearch } from 'lucide-react'
import type { SeatState } from '../types'
import { STATUS_COLOR, riskLevel } from '../lib/colors'
import { EmptyState } from './EmptyState'

export function SeatGrid({ seats }: { seats: Record<string, SeatState> }) {
  const ids = Object.keys(seats).sort()
  if (ids.length === 0) {
    return (
      <EmptyState
        icon={UserRoundSearch}
        title="Waiting for the first tracked student"
        body="Seats appear here as soon as the camera detects and seat-anchors someone. Each seat then runs its own ~20 second baseline calibration before risk scoring starts."
      />
    )
  }
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
      {ids.map((id) => (
        <SeatCard key={id} id={id} seat={seats[id]} />
      ))}
    </div>
  )
}

/**
 * Glance-only card (Problem 1): seat label, status badge, risk bar. That's
 * it — no yaw_z, no confidence %, no fused-camera string. Everything that
 * used to render inline here now lives behind the click, on /seat/:seatId.
 */
function SeatCard({ id, seat }: { id: string; seat: SeatState }) {
  const navigate = useNavigate()
  const level = seat.calibrated ? riskLevel(seat.risk) : null
  const color = level ? STATUS_COLOR[level] : '#8b8578'
  const pct = seat.calibrated ? Math.min(100, seat.risk * 100) : (seat.progress ?? 0) * 100
  const badgeLabel = level ?? 'calibrating'

  return (
    <motion.button
      layout
      onClick={() => navigate(`/seat/${id}`)}
      animate={seat.flash ? { backgroundColor: ['#ff5a3622', 'transparent'] } : {}}
      transition={{ duration: 1.2 }}
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      className="rounded-2xl p-4 border text-left cursor-pointer relative overflow-hidden"
      style={{ borderColor: `${color}40` }}
    >
      {level === 'critical' && (
        <motion.div
          className="absolute inset-0 pointer-events-none"
          animate={{ boxShadow: ['inset 0 0 0px #ff5a3600', 'inset 0 0 30px #ff5a3655', 'inset 0 0 0px #ff5a3600'] }}
          transition={{ duration: 1.8, repeat: Infinity }}
        />
      )}
      <div className="flex items-center justify-between mb-3">
        <span className="font-bold text-sm">{id.replace('_', ' ').toUpperCase()}</span>
        <span className="text-[10px] mono uppercase px-2 py-0.5 rounded-full" style={{ background: `${color}22`, color }}>
          {badgeLabel}
        </span>
      </div>
      <div className="w-full h-1.5 rounded-full bg-white/6 overflow-hidden">
        <motion.div
          className="h-full rounded-full"
          style={{ background: color }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.5 }}
        />
      </div>
    </motion.button>
  )
}
