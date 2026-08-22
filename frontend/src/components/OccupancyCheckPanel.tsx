import { useEffect, useState } from 'react'
import { UserCheck, UserX, ShieldAlert } from 'lucide-react'
import { useLive } from '../state/LiveContext'
import { STATUS_COLOR } from '../lib/colors'

interface Assignment {
  seat_id: string
  occupant_label: string
}

// Occupancy mismatch detection (2026-08-23): a real comparison layer over
// data already computed — the uploaded seating chart (SeatingChartUpload)
// against the same live seat-calibration state every other view reads.
// Two honest mismatch types: a seat that should be occupied but shows no
// real detected person (absence, or the student sat elsewhere), and a
// seat showing a real detected person that ISN'T on the chart at all
// (unauthorized/extra occupancy, or a seating-plan violation). No face
// identity involved anywhere — this only ever compares SEAT occupancy,
// never who's in it.
export function OccupancyCheckPanel() {
  const { seats } = useLive()
  const [assignments, setAssignments] = useState<Assignment[] | null>(null)

  useEffect(() => {
    fetch('/api/seating-chart')
      .then((r) => r.json())
      .then((d) => setAssignments(d.assignments ?? []))
      .catch(() => setAssignments([]))
  }, [])

  if (assignments === null) return null
  if (assignments.length === 0) return null

  const assignedSeatIds = new Set(assignments.map((a) => a.seat_id))
  const missing = assignments.filter((a) => !seats[a.seat_id]?.calibrated)
  const unexpected = Object.keys(seats).filter((seatId) => seats[seatId]?.calibrated && !assignedSeatIds.has(seatId))
  const matched = assignments.length - missing.length

  return (
    <div className="rounded-2xl border border-white/8 p-4 mb-6 bg-white/3">
      <div className="flex items-center gap-2 mb-3">
        <UserCheck size={14} className="text-white/50" />
        <h2 className="text-[11px] mono uppercase tracking-widest text-white/40">occupancy check — seating chart vs. real detection</h2>
      </div>
      <div className="flex items-center gap-4 mb-3 text-[11px] mono">
        <span style={{ color: STATUS_COLOR.calm }}>{matched}/{assignments.length} matched</span>
        {missing.length > 0 && <span style={{ color: STATUS_COLOR.watch }}>{missing.length} not detected</span>}
        {unexpected.length > 0 && <span style={{ color: STATUS_COLOR.critical }}>{unexpected.length} unexpected</span>}
      </div>
      {missing.length === 0 && unexpected.length === 0 ? (
        <p className="text-[11px] text-white/40">every assigned seat matches real detection — no mismatches</p>
      ) : (
        <div className="space-y-1.5">
          {missing.map((a) => (
            <div key={a.seat_id} className="flex items-center gap-2 text-[11px] px-2.5 py-1.5 rounded-lg" style={{ background: `${STATUS_COLOR.watch}10` }}>
              <UserX size={12} style={{ color: STATUS_COLOR.watch }} />
              <span className="text-white/70">{a.seat_id.toUpperCase()} assigned to <b>{a.occupant_label}</b> — not detected</span>
            </div>
          ))}
          {unexpected.map((seatId) => (
            <div key={seatId} className="flex items-center gap-2 text-[11px] px-2.5 py-1.5 rounded-lg" style={{ background: `${STATUS_COLOR.critical}10` }}>
              <ShieldAlert size={12} style={{ color: STATUS_COLOR.critical }} />
              <span className="text-white/70">{seatId.toUpperCase()} has a detected occupant not on the seating chart</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
