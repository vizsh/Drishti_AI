import { useEffect, useState } from 'react'
import { Database } from 'lucide-react'

interface FeedbackSummary {
  total_labels: number
  by_resolution: Record<string, number>
  by_signal_type: Record<string, number>
  recent: { seat_id: string; signal_type: string; object_label: string | null; confidence: number | null; resolution: string; created_at: string | null }[]
}

const RESOLUTION_LABEL: Record<string, string> = {
  false_alarm: 'false alarm',
  confirmed: 'confirmed',
  no_action: 'no action',
}

// Product audit §7.1 (2026-08-22): every alert resolution an invigilator
// makes is now persisted as a structured label (signal type + confidence +
// human verdict), not just a baseline-widening side effect. This panel is
// the concrete evidence for "every hour of use makes the next model
// better" — a real, growing count from backend/db.py's FeedbackLabel table,
// not a promise.
export function TrainingSignalPanel() {
  const [data, setData] = useState<FeedbackSummary | null>(null)

  useEffect(() => {
    async function poll() {
      try {
        const res = await fetch('/api/analytics/feedback-labels')
        setData(await res.json())
      } catch {
        /* keep last known */
      }
    }
    poll()
    const id = setInterval(poll, 5000)
    return () => clearInterval(id)
  }, [])

  const total = data?.total_labels ?? 0

  return (
    <div className="rounded-2xl border border-white/8 p-5 mb-6 bg-white/3">
      <div className="flex items-center gap-2 mb-1">
        <Database size={14} className="text-white/50" />
        <h2 className="text-sm font-bold uppercase tracking-wide">Training signal captured</h2>
      </div>
      <p className="text-[11px] mono text-white/40 mb-4">
        every alert resolution is a real, labeled example — which signal fired, at what confidence, and what an
        invigilator said really happened — feeding the object-detector and behaviour-classifier work ahead
      </p>
      <div className="flex items-center gap-6 mb-4">
        <div>
          <div className="text-2xl font-bold">{total}</div>
          <div className="text-[10px] mono uppercase tracking-widest text-white/35">labels this deployment</div>
        </div>
        {total > 0 && (
          <div className="flex gap-4 text-[11px] text-white/60">
            {Object.entries(data?.by_resolution ?? {}).map(([res, count]) => (
              <div key={res}>
                <span className="font-bold text-white/90">{count}</span> {RESOLUTION_LABEL[res] ?? res}
              </div>
            ))}
          </div>
        )}
      </div>
      {total === 0 ? (
        <p className="text-xs text-white/30">
          no labels yet — resolving a real alert as false alarm, confirmed, or no action starts populating this
        </p>
      ) : (
        <div className="rounded-xl border border-white/6 overflow-hidden">
          <table className="w-full text-[11px]">
            <tbody>
              {data!.recent.slice(0, 6).map((r, i) => (
                <tr key={i} className="border-b border-white/5 last:border-b-0">
                  <td className="px-3 py-1.5 mono text-white/40 whitespace-nowrap">{r.seat_id.toUpperCase()}</td>
                  <td className="px-3 py-1.5 text-white/60">
                    {r.signal_type}{r.object_label ? ` · ${r.object_label}` : ''}
                    {r.confidence != null ? ` · ${(r.confidence * 100).toFixed(0)}%` : ''}
                  </td>
                  <td className="px-3 py-1.5 text-right font-semibold" style={{ color: r.resolution === 'confirmed' ? '#ff5a36' : r.resolution === 'false_alarm' ? '#8dff9e' : '#c9cbc6' }}>
                    {RESOLUTION_LABEL[r.resolution] ?? r.resolution}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
