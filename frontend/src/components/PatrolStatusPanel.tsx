import { useEffect, useState } from 'react'
import { Footprints, ShieldAlert } from 'lucide-react'
import { useHallScope } from '../state/useHallScope'
import { STATUS_COLOR } from '../lib/colors'

interface CheckIn {
  hall: string
  invigilator: string
  checked_in_at: string
  minutes_ago: number
}

const STALE_MINUTES = 20

// Invigilator presence/patrol tracking (2026-08-23): a manual check-in,
// deliberately simple — not a wearable, not a location system. When a
// hall's human coverage is genuinely thin (no check-in in a while),
// that's exactly the moment the AI's own coverage is most load-bearing,
// and it's worth being able to show that honestly rather than only ever
// presenting the AI as a strict addition on top of full human coverage.
export function PatrolStatusPanel() {
  const { halls } = useHallScope()
  const [checkins, setCheckins] = useState<CheckIn[]>([])
  const [checkingIn, setCheckingIn] = useState<string | null>(null)

  function refresh() {
    fetch('/api/patrol/status')
      .then((r) => r.json())
      .then((d) => setCheckins(d.halls))
      .catch(() => {})
  }

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 30000)
    return () => clearInterval(id)
  }, [])

  async function checkIn(hall: string) {
    setCheckingIn(hall)
    try {
      await fetch('/api/patrol/check-in', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hall }),
      })
      refresh()
    } finally {
      setCheckingIn(null)
    }
  }

  if (halls.length === 0) return null

  return (
    <div className="rounded-2xl border border-white/8 p-4 mb-6 bg-white/3">
      <div className="flex items-center gap-2 mb-3">
        <Footprints size={14} className="text-white/50" />
        <h2 className="text-[11px] mono uppercase tracking-widest text-white/40">invigilator patrol — real human coverage, not assumed</h2>
      </div>
      <div className="flex flex-wrap gap-2.5">
        {halls.map((hall) => {
          const checkin = checkins.find((c) => c.hall === hall)
          const stale = !checkin || checkin.minutes_ago > STALE_MINUTES
          return (
            <div
              key={hall}
              className="flex items-center gap-2.5 rounded-xl border px-3 py-2"
              style={{ borderColor: stale ? `${STATUS_COLOR.watch}40` : 'rgba(255,255,255,0.08)', background: stale ? `${STATUS_COLOR.watch}0c` : 'transparent' }}
            >
              <div>
                <div className="text-[11px] font-bold">{hall}</div>
                <div className="text-[10px] mono flex items-center gap-1" style={{ color: stale ? STATUS_COLOR.watch : 'rgba(255,255,255,0.4)' }}>
                  {stale && <ShieldAlert size={9} />}
                  {checkin
                    ? `last patrol ${checkin.minutes_ago < 1 ? 'just now' : `${Math.round(checkin.minutes_ago)}m ago`} · ${checkin.invigilator}`
                    : 'no check-in recorded yet'}
                </div>
              </div>
              <button
                onClick={() => checkIn(hall)}
                disabled={checkingIn === hall}
                className="text-[10px] mono uppercase px-2.5 py-1.5 rounded-lg border border-white/15 hover:border-white/30 text-white/70 disabled:opacity-50 shrink-0"
              >
                {checkingIn === hall ? '…' : 'check in'}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
