import { useEffect, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ShieldCheck, ShieldAlert, RefreshCw } from 'lucide-react'

interface CoverageResult {
  seat_id: string
  covered: boolean
  covering_cameras: string[]
  reason: string | null
}

export function CoveragePanel() {
  const [results, setResults] = useState<CoverageResult[]>([])
  const [loading, setLoading] = useState(false)
  const [loaded, setLoaded] = useState(false)

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

  const gaps = results.filter((r) => !r.covered).length

  return (
    <div className="rounded-3xl border border-white/8 p-5 mb-6" style={{ background: 'linear-gradient(180deg, #ffffff06, #ffffff01)' }}>
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
        <p className="text-xs mono" style={{ color: gaps === 0 ? '#8dff9e' : '#ff5a36' }}>
          {gaps === 0
            ? `All ${results.length} seats covered — safe to start.`
            : `${gaps} of ${results.length} seats have NO camera coverage — resolve before starting the exam.`}
        </p>
      )}
    </div>
  )
}
