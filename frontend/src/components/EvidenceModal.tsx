import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { X, Pause, Play } from 'lucide-react'

interface Manifest {
  fps: number
  frame_count: number
  frames: string[]
}

export function EvidenceModal({ url, onClose }: { url: string | null; onClose: () => void }) {
  const [manifest, setManifest] = useState<Manifest | null>(null)
  const [idx, setIdx] = useState(0)
  const [playing, setPlaying] = useState(true)
  const [status, setStatus] = useState('')
  const baseUrl = url ? url.replace(/manifest\.json.*$/, '') : ''

  useEffect(() => {
    if (!url) return
    setManifest(null)
    setIdx(0)
    setStatus('loading clip…')
    fetch(`${url}?t=${Date.now()}`)
      .then((r) => {
        if (!r.ok) throw new Error('not ready')
        return r.json()
      })
      .then((m) => {
        setManifest(m)
        setStatus('')
      })
      .catch(() => setStatus('clip still encoding — close and reopen in a moment'))
  }, [url])

  useEffect(() => {
    if (!manifest || !playing) return
    const id = setInterval(() => {
      setIdx((i) => (i + 1) % manifest.frames.length)
    }, 1000 / (manifest.fps || 10))
    return () => clearInterval(id)
  }, [manifest, playing])

  return (
    <AnimatePresence>
      {url && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: '#000000b8', backdropFilter: 'blur(6px)' }}
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            onClick={(e) => e.stopPropagation()}
            className="rounded-2xl border border-white/10 p-4 max-w-2xl w-full"
            style={{ background: '#0a0a0d' }}
          >
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="text-sm font-bold">Evidence clip</h3>
                <p className="text-[10px] mono text-white/40">faces auto-blurred before storage · this view is logged for audit purposes</p>
              </div>
              <button onClick={onClose} className="text-white/50 hover:text-white"><X size={18} /></button>
            </div>
            <div className="rounded-xl overflow-hidden bg-black flex items-center justify-center" style={{ aspectRatio: '16/9' }}>
              {manifest && manifest.frames[idx] ? (
                <img src={baseUrl + manifest.frames[idx]} className="max-w-full max-h-full" />
              ) : (
                <span className="text-xs mono text-white/40">{status}</span>
              )}
            </div>
            {manifest && (
              <div className="flex items-center justify-center gap-3 mt-3">
                <button
                  onClick={() => setPlaying((p) => !p)}
                  className="flex items-center gap-1.5 text-xs mono px-3 py-1.5 rounded-md border border-white/12"
                >
                  {playing ? <Pause size={12} /> : <Play size={12} />} {playing ? 'pause' : 'play'}
                </button>
                <span className="text-[10px] mono text-white/40">{manifest.frame_count} frames · {manifest.fps} fps</span>
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
