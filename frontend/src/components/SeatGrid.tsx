import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { UserRoundSearch, Volume2 } from 'lucide-react'
import type { SeatState } from '../types'
import { STATUS_COLOR, riskLevel } from '../lib/colors'
import { humanizeRisk, humanizeCalibration, humanizeYaw } from '../lib/humanize'
import { EmptyState } from './EmptyState'

/**
 * Product redesign (2026-08-21): seat cards are now "glance-only" tiles.
 * No z-scores, no raw confidence %. Just:
 *   - Seat label
 *   - Human-readable status ("All clear" / "Elevated activity" / "Verification required")
 *   - A subtle behavior hint ("Facing forward" / "Glancing right")
 *   - Color-coded risk bar
 *   - Pulse animation during calibration instead of a raw progress number
 *
 * Technical details live behind the click on /seat/:seatId.
 */
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

function SeatCard({ id, seat }: { id: string; seat: SeatState }) {
  const navigate = useNavigate()
  const level = seat.calibrated ? riskLevel(seat.risk) : null
  const color = level ? STATUS_COLOR[level] : '#8b8578'
  const pct = seat.calibrated ? Math.min(100, seat.risk * 100) : (seat.progress ?? 0) * 100

  // Human-readable labels instead of raw numbers
  const statusLabel = seat.calibrated ? humanizeRisk(seat.risk) : humanizeCalibration(seat.progress ?? 0)
  const behaviorHint = seat.calibrated ? humanizeYaw(seat.yawZ) : null

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
      {/* Critical pulse glow */}
      {level === 'critical' && (
        <motion.div
          className="absolute inset-0 pointer-events-none"
          animate={{ boxShadow: ['inset 0 0 0px #ff5a3600', 'inset 0 0 30px #ff5a3655', 'inset 0 0 0px #ff5a3600'] }}
          transition={{ duration: 1.8, repeat: Infinity }}
        />
      )}

      {/* Calibrating pulse */}
      {!seat.calibrated && (
        <motion.div
          className="absolute inset-0 pointer-events-none"
          animate={{ opacity: [0.03, 0.08, 0.03] }}
          transition={{ duration: 2.5, repeat: Infinity, ease: 'easeInOut' }}
          style={{ background: '#8b8578' }}
        />
      )}

      {/* Header row */}
      <div className="flex items-center justify-between mb-2">
        <span className="font-bold text-sm">{id.replace('_', ' ').toUpperCase()}</span>
        {level === 'critical' && (
          <Volume2 size={12} className="text-critical animate-pulse" />
        )}
      </div>

      {/* Status label — human readable */}
      <p className="text-xs mb-1" style={{ color }}>
        {statusLabel}
      </p>

      {/* Behavior hint — only when calibrated */}
      {behaviorHint && (
        <p className="text-[10px] mono text-white/35 mb-2">{behaviorHint}</p>
      )}

      {/* Risk bar */}
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
