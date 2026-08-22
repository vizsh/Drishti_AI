import { Eye, EyeOff, ScanEye } from 'lucide-react'
import { useLive } from '../state/LiveContext'
import { useHallScope } from '../state/useHallScope'
import { humanizeConfidence } from '../lib/humanize'

const HUD_CYAN = '#5ad1ff'

// Per-seat monitoring-confidence map (2026-08-23): the honest complement
// to everything else this project does — not "the AI watches every seat
// equally well," but "here's exactly where its own view is weaker, so a
// human knows where to put their attention." Deliberately does NOT reuse
// calm/watch/critical (the one-urgency-color rule audited this session):
// low AI confidence isn't a behavioral alert, it's a completely different
// axis, and coloring it the same as risk would make it look like one.
// Uses the same informational HUD cyan the room-scan/digital-twin views
// already established for "sensing," never for urgency.
export function MonitoringConfidenceMap() {
  const { seats } = useLive()
  const { cameras, halls } = useHallScope()

  const hallsWithSeats = halls
    .map((hall) => ({ hall, seatIds: [...new Set(cameras.filter((c) => c.hall === hall).flatMap((c) => c.seats))].sort() }))
    .filter((h) => h.seatIds.length > 0)

  if (hallsWithSeats.length === 0) return null

  return (
    <div className="rounded-2xl border border-white/8 p-4 mb-6 bg-white/3">
      <div className="flex items-center gap-2 mb-1">
        <ScanEye size={14} className="text-white/50" />
        <h2 className="text-[11px] mono uppercase tracking-widest text-white/40">monitoring confidence — where the AI's own view is weaker</h2>
      </div>
      <p className="text-[11px] text-white/40 mb-3 max-w-2xl">
        Not a risk signal — a seat can be perfectly calm and still have a weak view (back row, extreme angle, partial
        occlusion). Weak-view seats are exactly where an invigilator's own attention matters most.
      </p>
      {hallsWithSeats.map(({ hall, seatIds }) => (
        <div key={hall} className="mb-3 last:mb-0">
          <div className="text-[10px] mono text-white/30 uppercase mb-1.5">{hall}</div>
          <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 xl:grid-cols-10 gap-2">
            {seatIds.map((seatId) => {
              const seat = seats[seatId]
              const conf = seat?.confidence
              const known = conf != null
              const strong = known && conf >= 0.6
              const weak = known && conf < 0.4
              const Icon = !known ? EyeOff : weak ? EyeOff : Eye
              return (
                <div
                  key={seatId}
                  className="aspect-square rounded-lg flex flex-col items-center justify-center gap-0.5"
                  style={{
                    background: known ? `${HUD_CYAN}${Math.round((conf as number) * 35).toString(16).padStart(2, '0')}` : 'transparent',
                    border: `1px solid ${known ? `${HUD_CYAN}${strong ? '80' : weak ? '30' : '55'}` : '#ffffff14'}`,
                  }}
                  title={known ? `${seatId} — ${humanizeConfidence(conf).label} (${Math.round((conf as number) * 100)}%)` : `${seatId} — not currently tracked`}
                >
                  <Icon size={11} style={{ color: known ? HUD_CYAN : '#ffffff30' }} />
                  <span className="text-[7px] mono" style={{ color: known ? HUD_CYAN : '#ffffff30' }}>
                    {known ? `${Math.round((conf as number) * 100)}%` : seatId.replace('seat_', '')}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}
