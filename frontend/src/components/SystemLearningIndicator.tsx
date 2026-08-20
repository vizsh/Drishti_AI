import { useEffect, useState } from 'react'
import { Brain } from 'lucide-react'
import { useHallScope } from '../state/useHallScope'

interface Analytics {
  total_alerts: number
  false_positives_dismissed: number
}

// Phase 5: a visible, real stat for "the system is learning" — every
// false_alarm resolution (backend/pipeline_worker.py's resolve_alert)
// widens that seat's calibration baseline, and this count is the same
// false_positives_dismissed field /api/analytics already computes from the
// feedback event log (backend/db.py's analytics_summary). No separate
// simulated counter — dismissing a real alert as a false alarm moves this
// number.
export function SystemLearningIndicator() {
  const [data, setData] = useState<Analytics | null>(null)
  const { scopedSeatIds } = useHallScope()
  const scopeKey = [...scopedSeatIds].sort().join(',')

  useEffect(() => {
    async function poll() {
      try {
        const params = scopeKey ? `?seat_ids=${scopeKey}` : ''
        const res = await fetch(`/api/analytics${params}`)
        setData(await res.json())
      } catch {
        /* keep last known */
      }
    }
    poll()
    const id = setInterval(poll, 4000)
    return () => clearInterval(id)
  }, [scopeKey])

  const dismissed = data?.false_positives_dismissed ?? 0

  return (
    <div className="rounded-2xl border border-white/8 px-5 py-4 mb-6 flex items-center gap-4" style={{ background: 'linear-gradient(180deg, #5ad1ff10, #5ad1ff02)' }}>
      <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0" style={{ background: '#5ad1ff22' }}>
        <Brain size={18} color="#5ad1ff" />
      </div>
      <div>
        <div className="text-[10px] mono uppercase tracking-widest text-white/40">system learning</div>
        <div className="text-sm text-white/80">
          <span className="font-bold text-white">{dismissed}</span> false-positive{dismissed === 1 ? '' : 's'} dismissed this session
          {dismissed > 0 && <span className="text-white/50"> — that many seats' baselines have been widened, reducing repeat false alarms</span>}
        </div>
      </div>
    </div>
  )
}
