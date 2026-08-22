import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ShieldCheck } from 'lucide-react'
import type { SeatState, AlertItem } from '../types'
import { STATUS_COLOR, riskLevel } from '../lib/colors'

// KEYFRAME-inspired seat-map tile view (product audit §6, closed out
// 2026-08-23): a privacy-forward alternative to camera thumbnails —
// abstract colored squares, one per seat, no video frame at all. Where
// the camera grid answers "what does this room look like," this answers
// "which seats need attention" as fast as possible, with nothing on
// screen that could be mistaken for surveillance footage. Same
// calm-by-default escalation rule as every other live view: a tile only
// leaves calm once a real, notify-worthy alert exists for that seat.
export function SeatMapTileGrid({
  seatIds,
  seats,
  latestAlertBySeat,
}: {
  seatIds: string[]
  seats: Record<string, SeatState>
  latestAlertBySeat: Map<string, AlertItem>
}) {
  const navigate = useNavigate()

  return (
    <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 xl:grid-cols-10 gap-2.5">
      {seatIds.map((seatId) => (
        <SeatTile
          key={seatId}
          seatId={seatId}
          seat={seats[seatId]}
          alert={latestAlertBySeat.get(seatId) ?? null}
          onClick={() => navigate(`/seat/${seatId}`)}
        />
      ))}
    </div>
  )
}

function SeatTile({
  seatId,
  seat,
  alert,
  onClick,
}: {
  seatId: string
  seat: SeatState | undefined
  alert: AlertItem | null
  onClick: () => void
}) {
  const sensed = !!seat
  const alerted = !!alert
  const level = alerted && seat?.calibrated ? riskLevel(seat.risk) : 'calm'
  const color = sensed ? STATUS_COLOR[level] : '#3a3f3a'

  return (
    <motion.button
      onClick={onClick}
      whileHover={{ scale: 1.06 }}
      whileTap={{ scale: 0.96 }}
      animate={alerted && level === 'critical' ? { boxShadow: [`0 0 0px ${color}00`, `0 0 14px ${color}90`, `0 0 0px ${color}00`] } : {}}
      transition={{ duration: 1.5, repeat: alerted && level === 'critical' ? Infinity : 0 }}
      className="aspect-square rounded-lg flex flex-col items-center justify-center relative"
      style={{
        background: sensed ? `${color}1c` : 'transparent',
        border: `1.5px solid ${sensed ? color : '#ffffff14'}`,
        opacity: sensed ? 1 : 0.4,
      }}
      title={alerted ? alert!.explanation : sensed ? 'all calm' : 'not currently tracked'}
    >
      {!sensed ? (
        <span className="text-[8px] mono text-white/25">{seatId.replace('seat_', '')}</span>
      ) : alerted ? (
        <span className="text-[9px] font-bold mono" style={{ color }}>{seatId.replace('seat_', '')}</span>
      ) : (
        <>
          <ShieldCheck size={11} style={{ color }} className="mb-0.5 opacity-70" />
          <span className="text-[7px] mono text-white/40">{seatId.replace('seat_', '')}</span>
        </>
      )}
    </motion.button>
  )
}
