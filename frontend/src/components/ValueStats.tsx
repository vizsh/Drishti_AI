import { useEffect, useState } from 'react'
import { ShieldCheck, Radar, TrendingDown, Bell } from 'lucide-react'
import { useHallScope } from '../state/useHallScope'

interface CoverageResult {
  seat_id: string
  covered: boolean
}
interface CalibrationQuality {
  camera_id: string
  status: 'gathering' | 'good' | 'needs_attention'
}
interface Analytics {
  total_alerts: number
  false_positives_dismissed: number
}

// Part 4 (product-conviction pass, 2026-08-21): the same numbers already
// computed by /api/coverage, /api/calibration-quality, and /api/analytics,
// restated as short outcome sentences instead of raw stat tiles — a buyer
// evaluating this product should see what it's DONE, not just what it
// measures. Every sentence here is a real current-session number, not
// decorative copy.
export function ValueStats() {
  const [coverage, setCoverage] = useState<CoverageResult[] | null>(null)
  const [quality, setQuality] = useState<CalibrationQuality[]>([])
  const [analytics, setAnalytics] = useState<Analytics | null>(null)
  const { scopedSeatIds } = useHallScope()
  const scopeKey = [...scopedSeatIds].sort().join(',')

  useEffect(() => {
    fetch('/api/coverage').then((r) => r.json()).then((d) => setCoverage(d.results ?? []))
  }, [])

  useEffect(() => {
    async function poll() {
      try {
        const [q, a] = await Promise.all([
          fetch('/api/calibration-quality').then((r) => r.json()),
          fetch(`/api/analytics${scopeKey ? `?seat_ids=${scopeKey}` : ''}`).then((r) => r.json()),
        ])
        setQuality(q.cameras ?? [])
        setAnalytics(a)
      } catch {
        /* keep last known */
      }
    }
    poll()
    const id = setInterval(poll, 6000)
    return () => clearInterval(id)
  }, [scopeKey])

  if (!coverage || !analytics) return null

  const totalSeats = coverage.length
  const coveredSeats = coverage.filter((c) => c.covered).length
  const coveragePct = totalSeats > 0 ? Math.round((coveredSeats / totalSeats) * 100) : 0

  const judgedCameras = quality.filter((q) => q.status !== 'gathering')
  const goodCameras = judgedCameras.filter((q) => q.status === 'good').length

  const dismissed = analytics.false_positives_dismissed
  const totalAlerts = analytics.total_alerts

  const items: { icon: typeof ShieldCheck; text: string; tone: 'calm' | 'watch' | 'neutral' }[] = [
    {
      icon: ShieldCheck,
      text:
        coveragePct === 100
          ? `${coveragePct}% seat coverage verified before exam start`
          : `${coveragePct}% seat coverage — ${totalSeats - coveredSeats} seat${totalSeats - coveredSeats === 1 ? '' : 's'} still need${totalSeats - coveredSeats === 1 ? 's' : ''} a camera`,
      tone: coveragePct === 100 ? 'calm' : 'watch',
    },
  ]

  if (judgedCameras.length > 0) {
    items.push({
      icon: Radar,
      text: `${goodCameras} of ${judgedCameras.length} camera${judgedCameras.length === 1 ? '' : 's'} calibrated with a healthy seat-anchor accuracy`,
      tone: goodCameras === judgedCameras.length ? 'calm' : 'watch',
    })
  }

  if (totalAlerts > 0) {
    const fpRate = Math.round((dismissed / totalAlerts) * 100)
    items.push({
      icon: TrendingDown,
      text: `${fpRate}% of this session's alerts dismissed as false positives — each one widened that seat's baseline`,
      tone: 'neutral',
    })
  }

  items.push({
    icon: Bell,
    text: `${totalAlerts} alert${totalAlerts === 1 ? '' : 's'} this session, every one scored against each student's own calibrated baseline`,
    tone: 'neutral',
  })

  return (
    <div className="flex flex-wrap gap-2 mb-6">
      {items.map((it, i) => (
        <div
          key={i}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-full text-[11px] mono border ${
            it.tone === 'calm' ? 'border-calm/30 text-calm bg-calm/8' : it.tone === 'watch' ? 'border-watch/30 text-watch bg-watch/8' : 'border-white/12 text-white/60'
          }`}
        >
          <it.icon size={12} className="shrink-0" />
          {it.text}
        </div>
      ))}
    </div>
  )
}
