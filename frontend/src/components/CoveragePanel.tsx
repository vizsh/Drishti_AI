import { useEffect, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ShieldCheck, ShieldAlert, RefreshCw, ChevronDown, ChevronUp, Radar } from 'lucide-react'

interface CoverageResult {
  seat_id: string
  covered: boolean
  covering_cameras: string[]
  reason: string | null
}

interface CalibrationQuality {
  camera_id: string
  hit_rate: number | null
  sample_count: number
  status: 'gathering' | 'good' | 'needs_attention'
}

const QUALITY_COPY: Record<CalibrationQuality['status'], { label: string; color: string }> = {
  gathering: { label: 'gathering data…', color: '#8b8578' },
  good: { label: 'calibration looks good', color: '#8dff9e' },
  needs_attention: { label: 'calibration needs attention', color: '#ff5a36' },
}

export function CoveragePanel() {
  const [results, setResults] = useState<CoverageResult[]>([])
  const [loading, setLoading] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [quality, setQuality] = useState<CalibrationQuality[]>([])
  const [showTechnical, setShowTechnical] = useState<string | null>(null)

  const run = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/coverage')
      const data = await res.json()
      setResults(data.results ?? [])
      setLoaded(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { run() }, [run])

  useEffect(() => {
    async function poll() {
      try {
        const res = await fetch('/api/calibration-quality')
        const data = await res.json()
        setQuality(data.cameras ?? [])
      } catch {
        /* keep last known */
      }
    }
    poll()
    const id = setInterval(poll, 5000)
    return () => clearInterval(id)
  }, [])

  const gaps = results.filter((r) => !r.covered).length

  return (
    <div className="rounded-2xl border border-white/8 p-5 mb-6" style={{ background: 'linear-gradient(180deg, #ffffff06, #ffffff01)' }}>
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wide">Pre-exam setup — camera coverage</h2>
          <p className="text-[11px] mono text-white/40 mt-0.5">run before the exam starts · flags blind spots before a student goes unmonitored</p>
        </div>
        <button
          onClick={run}
          className="flex items-center gap-1.5 text-[11px] mono uppercase px-3 py-1.5 rounded-full border border-white/15 hover:border-white/30 transition"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> run check
        </button>
      </div>
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 mb-3">
        <AnimatePresence>
          {results.map((r) => (
            <motion.div
              key={r.seat_id}
              layout
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              className="rounded-xl p-3 text-center border"
              style={{
                borderColor: r.covered ? '#8dff9e35' : '#ff5a3645',
                background: r.covered ? '#8dff9e0a' : '#ff5a360f',
              }}
            >
              <div className="flex justify-center mb-1">
                {r.covered ? <ShieldCheck size={16} color="#8dff9e" /> : <ShieldAlert size={16} color="#ff5a36" />}
              </div>
              <div className="text-[11px] font-bold">{r.seat_id.replace('_', ' ').toUpperCase()}</div>
              <div className="text-[9px] mono mt-0.5" style={{ color: r.covered ? '#8dff9e' : '#ff5a36' }}>
                {r.covered ? 'covered' : 'blind spot'}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
      {loaded && (
        <p className="text-xs mono mb-4" style={{ color: gaps === 0 ? '#8dff9e' : '#ff5a36' }}>
          {gaps === 0
            ? `All ${results.length} seats covered — safe to start.`
            : `${gaps} of ${results.length} seats have NO camera coverage — resolve before starting the exam.`}
        </p>
      )}

      {quality.length > 0 && (
        <div className="border-t border-white/8 pt-4">
          <div className="flex items-center gap-2 mb-3">
            <Radar size={13} className="text-white/40" />
            <h3 className="text-xs font-bold uppercase tracking-wide text-white/70">Calibration quality — live</h3>
          </div>
          <div className="flex flex-col gap-2">
            {quality.map((q) => {
              const copy = QUALITY_COPY[q.status]
              const expanded = showTechnical === q.camera_id
              return (
                <div key={q.camera_id} className="rounded-xl border px-3 py-2" style={{ borderColor: `${copy.color}30`, background: `${copy.color}0a` }}>
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full shrink-0" style={{ background: copy.color }} />
                      <span className="text-xs font-semibold">{q.camera_id}</span>
                      <span className="text-xs mono" style={{ color: copy.color }}>{copy.label}</span>
                    </div>
                    {q.hit_rate != null && (
                      <button
                        onClick={() => setShowTechnical(expanded ? null : q.camera_id)}
                        className="flex items-center gap-1 text-[10px] mono text-white/35 hover:text-white/60"
                      >
                        {expanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />} technical detail
                      </button>
                    )}
                  </div>
                  {expanded && q.hit_rate != null && (
                    <p className="text-[10px] mono text-white/45 mt-2">
                      seat-anchor hit rate: {(q.hit_rate * 100).toFixed(0)}% over last {q.sample_count} detections
                      (flags below 40%)
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
