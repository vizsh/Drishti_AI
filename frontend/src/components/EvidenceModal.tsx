import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { X, Pause, Play, ChevronDown, ChevronUp } from 'lucide-react'

interface Annotation {
  xyxy: [number, number, number, number]
  keypoints: [number, number][]
  keypoint_confidence: number[]
}

interface Manifest {
  fps: number
  frame_count: number
  frames: string[]
  seat_id?: string | null
  annotations?: (Annotation | null)[]
}

// COCO-17 order, matches backend/pipeline_worker.py's SKELETON_EDGES.
const SKELETON_EDGES: [number, number][] = [
  [5, 6], [5, 7], [7, 9], [6, 8], [8, 10],
  [5, 11], [6, 12], [11, 12],
  [11, 13], [13, 15], [12, 14], [14, 16],
  [0, 5], [0, 6],
]
const MIN_KEYPOINT_CONF = 0.3

function AnnotationOverlay({
  naturalW,
  naturalH,
  current,
  trail,
}: {
  naturalW: number
  naturalH: number
  current: Annotation | null
  trail: Annotation[]
}) {
  if (!naturalW || !naturalH) return null
  const centers = trail
    .map((a) => a && [(a.xyxy[0] + a.xyxy[2]) / 2, (a.xyxy[1] + a.xyxy[3]) / 2])
    .filter((c): c is [number, number] => !!c)

  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none"
      viewBox={`0 0 ${naturalW} ${naturalH}`}
      preserveAspectRatio="xMidYMid meet"
    >
      {/* motion trail across the last few frames — a lightweight "where this
          came from" cue, not a full trajectory */}
      {centers.length > 1 && (
        <polyline
          points={centers.map((c) => c.join(',')).join(' ')}
          fill="none"
          stroke="#ffb648"
          strokeWidth={1.5}
          strokeDasharray="4 3"
          opacity={0.55}
        />
      )}
      {centers.length > 1 &&
        (() => {
          const [x1, y1] = centers[centers.length - 2]
          const [x2, y2] = centers[centers.length - 1]
          const angle = Math.atan2(y2 - y1, x2 - x1)
          const size = 7
          const tip: [number, number] = [x2, y2]
          const a1: [number, number] = [x2 - size * Math.cos(angle - 0.4), y2 - size * Math.sin(angle - 0.4)]
          const a2: [number, number] = [x2 - size * Math.cos(angle + 0.4), y2 - size * Math.sin(angle + 0.4)]
          return <polygon points={`${tip.join(',')} ${a1.join(',')} ${a2.join(',')}`} fill="#ffb648" opacity={0.85} />
        })()}
      {current && (
        <>
          <rect
            x={current.xyxy[0]}
            y={current.xyxy[1]}
            width={current.xyxy[2] - current.xyxy[0]}
            height={current.xyxy[3] - current.xyxy[1]}
            fill="none"
            stroke="#ff5a36"
            strokeWidth={2.5}
            rx={4}
          />
          {SKELETON_EDGES.map(([a, b], i) => {
            const ca = current.keypoint_confidence[a]
            const cb = current.keypoint_confidence[b]
            if (ca < MIN_KEYPOINT_CONF || cb < MIN_KEYPOINT_CONF) return null
            const [xa, ya] = current.keypoints[a]
            const [xb, yb] = current.keypoints[b]
            return <line key={i} x1={xa} y1={ya} x2={xb} y2={yb} stroke="#ff5a36" strokeWidth={2} opacity={0.9} />
          })}
        </>
      )}
    </svg>
  )
}

export function EvidenceModal({ url, onClose }: { url: string | null; onClose: () => void }) {
  const [manifest, setManifest] = useState<Manifest | null>(null)
  const [idx, setIdx] = useState(0)
  const [playing, setPlaying] = useState(true)
  const [status, setStatus] = useState('')
  const [showTechnical, setShowTechnical] = useState(false)
  const [naturalSize, setNaturalSize] = useState({ w: 0, h: 0 })
  const imgRef = useRef<HTMLImageElement>(null)
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

  useEffect(() => {
    setNaturalSize({ w: 0, h: 0 })
    setShowTechnical(false)
  }, [url])

  const annotations = manifest?.annotations ?? []
  const currentAnnotation = annotations[idx] ?? null
  const trail = [annotations[idx - 2], annotations[idx - 1], annotations[idx]].filter(
    (a): a is Annotation => !!a
  )

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
                <div className="relative inline-flex max-w-full max-h-full">
                  <img
                    ref={imgRef}
                    src={baseUrl + manifest.frames[idx]}
                    className="max-w-full max-h-full block"
                    onLoad={(e) => {
                      const img = e.currentTarget
                      setNaturalSize({ w: img.naturalWidth, h: img.naturalHeight })
                    }}
                  />
                  {manifest.seat_id && (
                    <AnnotationOverlay
                      naturalW={naturalSize.w}
                      naturalH={naturalSize.h}
                      current={currentAnnotation}
                      trail={trail}
                    />
                  )}
                </div>
              ) : (
                <span className="text-xs mono text-white/40">{status}</span>
              )}
            </div>
            {manifest && manifest.seat_id && (
              <p className="text-[10px] mono text-white/35 mt-2">
                {currentAnnotation
                  ? `${manifest.seat_id.replace('seat_', 'seat ')} highlighted — box + pose tracked this frame`
                  : `${manifest.seat_id.replace('seat_', 'seat ')} not tracked in this frame`}
              </p>
            )}
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
            {manifest && currentAnnotation && (
              <div className="mt-3 border-t border-white/8 pt-2">
                <button
                  onClick={() => setShowTechnical((v) => !v)}
                  className="flex items-center gap-1 text-[10px] mono text-white/40 hover:text-white/70"
                >
                  {showTechnical ? <ChevronUp size={11} /> : <ChevronDown size={11} />} technical detail
                </button>
                {showTechnical && (
                  <div className="mt-2 text-[10px] mono text-white/50 space-y-0.5">
                    <div>
                      bbox (px): [{currentAnnotation.xyxy.map((v) => v.toFixed(0)).join(', ')}]
                    </div>
                    <div>
                      keypoints tracked: {currentAnnotation.keypoint_confidence.filter((c) => c >= MIN_KEYPOINT_CONF).length}/17
                      {' '}(≥{MIN_KEYPOINT_CONF} confidence)
                    </div>
                    <div>frame {idx + 1} of {manifest.frame_count}</div>
                  </div>
                )}
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
