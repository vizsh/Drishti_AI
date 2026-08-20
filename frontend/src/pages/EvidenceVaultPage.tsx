import { useEffect, useState } from 'react'
import { FolderOpen } from 'lucide-react'
import { EvidenceModal } from '../components/EvidenceModal'
import { useHallScope } from '../state/useHallScope'
import { seatColor } from '../lib/colors'

interface EventRow {
  id: number
  seat_id: string
  event_type: string
  sim_time: number
  risk_score: number | null
  explanation: string | null
  evidence_url: string | null
  created_at: string
}

export function EvidenceVaultPage() {
  const { isSeatInScope, scopedSeatIds } = useHallScope()
  const [entries, setEntries] = useState<EventRow[]>([])
  const [evidenceUrl, setEvidenceUrl] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/events?event_type=alert&limit=200')
      .then((r) => r.json())
      .then((d) => setEntries(d.events.filter((e: EventRow) => e.evidence_url)))
  }, [])

  const scoped = entries.filter((e) => isSeatInScope(e.seat_id))
  const seatIds = [...scopedSeatIds]

  return (
    <div>
      <div className="flex items-center gap-2 mb-1">
        <FolderOpen size={16} className="text-white/40" />
        <h1 className="text-lg font-bold">Evidence Vault</h1>
      </div>
      <p className="text-xs mono text-white/35 mb-6">
        face-blurred clips for every confirmed alert · every view is logged for audit purposes
      </p>

      {scoped.length === 0 ? (
        <div className="text-sm mono text-white/30 py-16 text-center">no evidence clips yet this session</div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {scoped.map((e) => (
            <button
              key={e.id}
              onClick={() => setEvidenceUrl(e.evidence_url)}
              className="rounded-2xl border border-white/8 p-4 text-left hover:border-white/25 transition-colors"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-bold" style={{ color: seatColor(e.seat_id, seatIds) }}>
                  {e.seat_id.toUpperCase()}
                </span>
                <span className="text-[10px] mono text-white/35">{e.sim_time.toFixed(1)}s</span>
              </div>
              <p className="text-[11px] text-white/60 leading-snug mb-2 line-clamp-3">{e.explanation}</p>
              <div className="flex items-center justify-between text-[10px] mono text-white/30">
                <span>risk {e.risk_score?.toFixed(2) ?? '—'}</span>
                <span style={{ color: '#5ad1ff' }}>▶ view clip</span>
              </div>
            </button>
          ))}
        </div>
      )}
      <EvidenceModal url={evidenceUrl} onClose={() => setEvidenceUrl(null)} />
    </div>
  )
}
