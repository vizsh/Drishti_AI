import { useEffect, useState, useCallback } from 'react'
import { RefreshCw } from 'lucide-react'
import { seatColor } from '../lib/colors'

interface EventRow {
  id: number
  seat_id: string
  event_type: string
  sim_time: number
  risk_score: number | null
  explanation: string | null
  evidence_url: string | null
}

const TYPE_STYLE: Record<string, { bg: string; color: string }> = {
  alert: { bg: '#ff5a3622', color: '#ff5a36' },
  gesture_alert: { bg: '#c4a3ff22', color: '#c4a3ff' },
  feedback: { bg: '#5ad1ff22', color: '#5ad1ff' },
  telemetry: { bg: '#ffffff14', color: '#8b8578' },
}

export function EventLog({ onViewEvidence }: { onViewEvidence: (url: string) => void }) {
  const [events, setEvents] = useState<EventRow[]>([])
  const [seatFilter, setSeatFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [search, setSearch] = useState('')
  const [knownSeats, setKnownSeats] = useState<string[]>([])

  const load = useCallback(async () => {
    const params = new URLSearchParams({ limit: '150' })
    if (seatFilter) params.set('seat_id', seatFilter)
    if (typeFilter) params.set('event_type', typeFilter)
    if (search) params.set('search', search)
    const res = await fetch(`/api/events?${params}`)
    const data = await res.json()
    setEvents(data.events)
    setKnownSeats((prev) => [...new Set([...prev, ...data.events.map((e: EventRow) => e.seat_id)])].sort())
  }, [seatFilter, typeFilter, search])

  useEffect(() => {
    load()
    const id = setInterval(load, 8000)
    return () => clearInterval(id)
  }, [load])

  return (
    <div className="mt-8">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h2 className="text-sm font-bold uppercase tracking-wide">
          Event log <span className="text-white/30 font-normal normal-case">— persisted, for invigilator review</span>
        </h2>
        <div className="flex items-center gap-2 flex-wrap">
          <select value={seatFilter} onChange={(e) => setSeatFilter(e.target.value)} className="bg-transparent border border-white/12 rounded-lg px-2 py-1.5 text-xs mono">
            <option value="">all seats</option>
            {knownSeats.map((s) => <option key={s} value={s}>{s.toUpperCase()}</option>)}
          </select>
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="bg-transparent border border-white/12 rounded-lg px-2 py-1.5 text-xs mono">
            <option value="">all types</option>
            <option value="alert">alert</option>
            <option value="gesture_alert">gesture</option>
            <option value="feedback">feedback</option>
            <option value="telemetry">telemetry</option>
          </select>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && load()}
            placeholder="search explanation…"
            className="bg-transparent border border-white/12 rounded-lg px-3 py-1.5 text-xs mono w-48"
          />
          <button onClick={load} className="flex items-center gap-1 text-xs mono px-3 py-1.5 rounded-lg border border-white/12" style={{ color: '#5ad1ff' }}>
            <RefreshCw size={12} /> refresh
          </button>
        </div>
      </div>
      <div className="rounded-2xl border border-white/8 overflow-hidden overflow-x-auto">
        <table className="w-full text-xs min-w-[600px]">
          <thead>
            <tr className="text-left text-white/35 mono border-b border-white/8">
              <th className="px-4 py-2 font-medium">time</th>
              <th className="px-4 py-2 font-medium">seat</th>
              <th className="px-4 py-2 font-medium">type</th>
              <th className="px-4 py-2 font-medium">risk</th>
              <th className="px-4 py-2 font-medium">detail</th>
            </tr>
          </thead>
          <tbody>
            {events.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-white/30 mono">no matching events</td></tr>
            )}
            {events.map((ev) => {
              const style = TYPE_STYLE[ev.event_type] ?? { bg: '#ffffff14', color: '#8b8578' }
              return (
                <tr key={ev.id} className="border-b border-white/5 hover:bg-white/[0.02]">
                  <td className="px-4 py-2 mono text-white/40">{ev.sim_time.toFixed(1)}s</td>
                  <td className="px-4 py-2 font-semibold" style={{ color: seatColor(ev.seat_id, knownSeats) }}>{ev.seat_id.toUpperCase()}</td>
                  <td className="px-4 py-2"><span className="text-[9px] mono px-1.5 py-0.5 rounded" style={{ background: style.bg, color: style.color }}>{ev.event_type}</span></td>
                  <td className="px-4 py-2 mono text-white/40">{ev.risk_score != null ? ev.risk_score.toFixed(2) : '—'}</td>
                  <td className="px-4 py-2 text-white/70">
                    {ev.explanation ?? '—'}
                    {ev.evidence_url && (
                      <button onClick={() => onViewEvidence(ev.evidence_url!)} className="ml-2 text-[10px] mono" style={{ color: '#5ad1ff' }}>▶ evidence</button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
