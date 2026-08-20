import { motion } from 'framer-motion'
import { Link2, Eye } from 'lucide-react'
import type { SeatState } from '../types'
import { LEVEL_COLOR, riskLevel } from '../lib/colors'

const LOW_CONFIDENCE_THRESHOLD = 0.4

export function SeatGrid({ seats }: { seats: Record<string, SeatState> }) {
  const ids = Object.keys(seats).sort()
  if (ids.length === 0) {
    return <div className="text-sm mono text-white/30 py-10 text-center">waiting for the first tracked student…</div>
  }
  return (
    <div className="grid grid-cols-2 gap-3">
      {ids.map((id) => (
        <SeatCard key={id} id={id} seat={seats[id]} />
      ))}
    </div>
  )
}

function SeatCard({ id, seat }: { id: string; seat: SeatState }) {
  const lowConfidence = seat.calibrated && seat.confidence != null && seat.confidence < LOW_CONFIDENCE_THRESHOLD
  const level = seat.calibrated ? riskLevel(seat.risk) : 'calibrating'
  const color = lowConfidence ? '#8b8578' : seat.calibrated ? LEVEL_COLOR[level] : '#8b8578'
  const pct = seat.calibrated ? Math.min(100, seat.risk * 100) : (seat.progress ?? 0) * 100
  const badge = !seat.calibrated ? 'calibrating' : lowConfidence ? 'low confidence' : level

  return (
    <motion.div
      layout
      animate={seat.flash ? { backgroundColor: ['#ff5a3622', 'transparent'] } : {}}
      transition={{ duration: 1.2 }}
      className="rounded-2xl p-4 border relative overflow-hidden"
      style={{ borderColor: `${color}40`, borderStyle: lowConfidence ? 'dashed' : 'solid' }}
    >
      {seat.calibrated && level === 'alert' && (
        <motion.div
          className="absolute inset-0 pointer-events-none"
          animate={{ boxShadow: ['inset 0 0 0px #ff5a3600', 'inset 0 0 30px #ff5a3655', 'inset 0 0 0px #ff5a3600'] }}
          transition={{ duration: 1.8, repeat: Infinity }}
        />
      )}
      <div className="flex items-center justify-between mb-2">
        <span className="font-bold text-sm">{id.replace('_', ' ').toUpperCase()}</span>
        <span className="text-[9px] mono uppercase px-2 py-0.5 rounded-full" style={{ background: `${color}22`, color }}>
          {badge}
        </span>
      </div>
      <div className="w-full h-1.5 rounded-full bg-white/6 overflow-hidden mb-2">
        <motion.div
          className="h-full rounded-full"
          style={{ background: color }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.5 }}
        />
      </div>
      <div className="flex justify-between text-[10px] mono text-white/40">
        <span>{seat.calibrated ? `risk ${seat.risk.toFixed(2)}` : `${pct.toFixed(0)}% settled`}</span>
        <span>{seat.calibrated && seat.yawZ != null ? `yaw_z ${seat.yawZ.toFixed(2)}` : ''}</span>
      </div>
      {seat.calibrated && seat.confidence != null && (
        <div className="mt-2 pt-2 border-t border-white/6 flex items-center justify-between text-[10px] mono text-white/40">
          <span className="flex items-center gap-1"><Eye size={11} /> confidence</span>
          <span>{(seat.confidence * 100).toFixed(0)}%</span>
        </div>
      )}
      {seat.cameras && seat.cameras.length > 1 && (
        <div className="flex items-center gap-1 text-[9px] mono mt-1" style={{ color: '#c4a3ff' }}>
          <Link2 size={10} /> fused: {seat.cameras.join(' + ')}
        </div>
      )}
    </motion.div>
  )
}
