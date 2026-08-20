import { useEffect, useState } from 'react'
import { seatColor } from '../lib/colors'

interface EventRow {
  seat_id: string
  event_type: string
  sim_time: number
  explanation: string | null
}

const TIMELINE_WINDOW_S = 300

export function SessionAnalytics() {
  const [heatmapTick, setHeatmapTick] = useState(Date.now())
  const [bySeat, setBySeat] = useState<Record<string, EventRow[]>>({})
  const [maxT, setMaxT] = useState(0)

  useEffect(() => {
    const id = setInterval(() => setHeatmapTick(Date.now()), 10000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    async function refresh() {
      try {
        const [a, g] = await Promise.all([
          fetch('/api/events?event_type=alert&limit=150').then((r) => r.json()),
          fetch('/api/events?event_type=gesture_alert&limit=150').then((r) => r.json()),
        ])
        const all: EventRow[] = [...a.events, ...g.events]
        const grouped: Record<string, EventRow[]> = {}
        let localMax = 0
        for (const ev of all) {
          ;(grouped[ev.seat_id] = grouped[ev.seat_id] ?? []).push(ev)
          localMax = Math.max(localMax, ev.sim_time)
        }
        setBySeat(grouped)
        setMaxT(localMax)
      } catch {
        /* keep last known state */
      }
    }
    refresh()
    const id = setInterval(refresh, 6000)
    return () => clearInterval(id)
  }, [])

  const windowStart = Math.max(0, maxT - TIMELINE_WINDOW_S)
  const seatIds = Object.keys(bySeat).sort()

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
      <div>
        <h2 className="text-sm font-bold uppercase tracking-wide mb-3">
          Motion heatmap <span className="text-white/30 font-normal normal-case">— session-wide</span>
        </h2>
        <div className="rounded-2xl overflow-hidden border border-white/8" style={{ aspectRatio: '4/3', background: '#000' }}>
          <img src={`/api/heatmap?t=${heatmapTick}`} className="w-full h-full object-cover" />
        </div>
        <p className="text-[10px] mono text-white/35 mt-2">accumulated frame-to-frame motion · where activity concentrated in the room</p>
      </div>
      <div className="md:col-span-2">
        <h2 className="text-sm font-bold uppercase tracking-wide mb-3">
          Activity timeline <span className="text-white/30 font-normal normal-case">— last 5 min, per seat</span>
        </h2>
        <div className="rounded-2xl border border-white/8 p-4">
          {seatIds.length === 0 ? (
            <div className="text-xs mono text-white/30 text-center py-8">no alert or gesture events yet this session</div>
          ) : (
            <div className="flex flex-col gap-2">
              {seatIds.map((seatId) => (
                <div key={seatId} className="flex items-center gap-3">
                  <span className="text-[10px] mono w-16 shrink-0" style={{ color: seatColor(seatId, seatIds) }}>
                    {seatId.toUpperCase()}
                  </span>
                  <div className="relative flex-1 h-4 rounded-full bg-white/5">
                    {bySeat[seatId].map((ev, i) => {
                      const pct = Math.min(100, Math.max(0, ((ev.sim_time - windowStart) / TIMELINE_WINDOW_S) * 100))
                      const color = ev.event_type === 'alert' ? '#ff5a36' : '#8b8578'
                      return (
                        <div
                          key={i}
                          className="absolute top-0 bottom-0 w-1 rounded-full"
                          style={{ left: `${pct}%`, background: color }}
                          title={`${ev.sim_time.toFixed(1)}s — ${ev.explanation ?? ''}`}
                        />
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="flex justify-between text-[9px] mono text-white/30 mt-3">
            <span>-{TIMELINE_WINDOW_S}s</span>
            <span>now ({maxT.toFixed(0)}s)</span>
          </div>
        </div>
      </div>
    </div>
  )
}
