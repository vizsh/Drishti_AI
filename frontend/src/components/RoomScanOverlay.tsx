import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { X, CheckCircle2, ScanLine, RotateCcw } from 'lucide-react'
import { useLive } from '../state/LiveContext'
import { STATUS_COLOR } from '../lib/colors'

const HUD_CYAN = '#5ad1ff'
const BOOT_LINES = ['SYSTEM INITIALIZING...', 'CALIBRATING LENS...', 'MAPPING SPACE...']
const SCAN_DURATION_S = 5

interface ScanSeat {
  seat_id: string
  status: 'visible' | 'partial' | 'occluded'
  confidence: number
  bbox: [number, number, number, number]
  hit_count: number
}

interface ScanResult {
  camera_id: string
  duration_seconds: number
  seats: ScanSeat[]
  coverage_pct: number
  visible_count: number
  partial_count: number
  occluded_count: number
  image_width: number
  image_height: number
}

const STATUS_LABEL: Record<ScanSeat['status'], string> = {
  visible: 'VISIBLE',
  partial: 'PARTIAL',
  occluded: 'OCCLUDED',
}
const STATUS_HEX: Record<ScanSeat['status'], string> = {
  visible: STATUS_COLOR.calm,
  partial: STATUS_COLOR.watch,
  occluded: STATUS_COLOR.critical,
}

type Stage = 'boot' | 'scanning' | 'reveal' | 'complete'

// Lab Setup room-scan (2026-08-22): every wireframe box, label, confidence
// number and coverage percentage this renders comes from POST /api/setup/
// cameras/{id}/scan (calibration/room_scan.py) — real detections during a
// live window, resolved to this camera's own configured seats via the
// exact same nearest_seat() homography the live pipeline scores against.
// The HUD boot sequence and staggered reveal are the only purely
// presentational parts; nothing here is a fabricated number.
export function RoomScanOverlay({ cameraId, onClose }: { cameraId: string; onClose: () => void }) {
  const { feedImages, setStreamMode } = useLive()
  const [stage, setStage] = useState<Stage>('boot')
  const [bootLine, setBootLine] = useState(0)
  const [progress, setProgress] = useState(0)
  const [result, setResult] = useState<ScanResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [frozenFrame, setFrozenFrame] = useState<string | null>(null)
  const startedRef = useRef(false)

  useEffect(() => {
    setStreamMode(cameraId, 'focused')
  }, [cameraId, setStreamMode])

  // Freeze whichever real frame is on screen the moment the scan begins,
  // so the boxes drawn afterward sit on the exact frame the camera saw —
  // not a live feed that's since moved on underneath static boxes.
  useEffect(() => {
    if (!frozenFrame && feedImages[cameraId]) setFrozenFrame(feedImages[cameraId])
  }, [cameraId, feedImages, frozenFrame])

  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true
    runScan()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function runScan() {
    setStage('boot')
    setError(null)
    setResult(null)
    setProgress(0)
    setBootLine(0)

    const lineTimer = setInterval(() => setBootLine((n) => Math.min(n + 1, BOOT_LINES.length - 1)), 500)
    const start = Date.now()
    const progressTimer = setInterval(() => {
      setProgress(Math.min(100, ((Date.now() - start) / (SCAN_DURATION_S * 1000)) * 100))
    }, 80)
    setTimeout(() => setStage('scanning'), 400)

    try {
      const res = await fetch(`/api/setup/cameras/${cameraId}/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ duration_seconds: SCAN_DURATION_S }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? `scan failed (${res.status})`)
      }
      const data: ScanResult = await res.json()
      clearInterval(lineTimer)
      clearInterval(progressTimer)
      setProgress(100)
      setResult(data)
      setStage('reveal')
      setTimeout(() => setStage('complete'), 900 + data.seats.length * 180)
    } catch (e) {
      clearInterval(lineTimer)
      clearInterval(progressTimer)
      setError(e instanceof Error ? e.message : 'scan failed')
    }
  }

  const imgW = result?.image_width ?? 1280
  const imgH = result?.image_height ?? 720
  const camIconX = imgW / 2
  const camIconY = imgH * 0.06

  return (
    <div className="fixed inset-0 z-[95] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="w-full max-w-3xl rounded-2xl border border-white/12 overflow-hidden" style={{ background: '#0a0a0d' }}>
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-white/8">
          <div className="flex items-center gap-2">
            <ScanLine size={15} style={{ color: HUD_CYAN }} />
            <span className="text-sm font-bold">Room scan — {cameraId}</span>
          </div>
          <button onClick={onClose} className="text-white/40 hover:text-white p-1.5 rounded-lg hover:bg-white/8">
            <X size={16} />
          </button>
        </div>

        <div className="relative" style={{ aspectRatio: `${imgW}/${imgH}`, background: '#000' }}>
          {/* Vignette + corner-bracket HUD frame, matching the reference
              clip's scanning-system look — chrome only, no data here. */}
          <div
            className="absolute inset-0 pointer-events-none z-20"
            style={{ boxShadow: 'inset 0 0 90px 30px rgba(0,0,0,0.75)' }}
          />
          {[
            { top: 10, left: 10, borderRight: 0, borderBottom: 0 },
            { top: 10, right: 10, borderLeft: 0, borderBottom: 0 },
            { bottom: 10, left: 10, borderRight: 0, borderTop: 0 },
            { bottom: 10, right: 10, borderLeft: 0, borderTop: 0 },
          ].map((pos, i) => (
            <div
              key={i}
              className="absolute w-6 h-6 border-2 z-20 pointer-events-none"
              style={{ ...pos, borderColor: `${HUD_CYAN}90` }}
            />
          ))}

          {frozenFrame ? (
            <img src={frozenFrame} className="w-full h-full object-cover opacity-80" />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-white/25 text-xs mono">
              waiting for a live frame from this camera…
            </div>
          )}

          {/* Boot HUD text + progress bar */}
          {(stage === 'boot' || stage === 'scanning') && (
            <div className="absolute top-4 left-4 z-30 mono text-[11px]" style={{ color: HUD_CYAN, textShadow: '0 0 8px #5ad1ff80' }}>
              {BOOT_LINES.slice(0, bootLine + 1).map((line, i) => (
                <div key={i}>{line}</div>
              ))}
              <div className="mt-1.5 w-40 h-1.5 rounded-full bg-white/10 overflow-hidden">
                <motion.div className="h-full" style={{ background: HUD_CYAN, width: `${progress}%` }} />
              </div>
            </div>
          )}

          {/* Real floor-grid + wireframe boxes + sightlines, drawn from
              the real scan result once it lands. */}
          {result && (stage === 'reveal' || stage === 'complete') && (
            <svg viewBox={`0 0 ${imgW} ${imgH}`} className="absolute inset-0 w-full h-full z-10">
              <motion.circle
                cx={camIconX}
                cy={camIconY}
                r={imgW * 0.012}
                fill={HUD_CYAN}
                initial={{ opacity: 0 }}
                animate={{ opacity: 0.9 }}
                transition={{ duration: 0.3 }}
              />
              {result.seats.map((seat, i) => {
                const [x1, y1, x2, y2] = seat.bbox
                const cx = (x1 + x2) / 2
                const cy = (y1 + y2) / 2
                const color = STATUS_HEX[seat.status]
                const delay = 0.5 + i * 0.18
                return (
                  <g key={seat.seat_id}>
                    <motion.line
                      x1={camIconX}
                      y1={camIconY}
                      x2={cx}
                      y2={cy}
                      stroke={color}
                      strokeWidth={imgW * 0.0015}
                      strokeDasharray="6 5"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 0.55 }}
                      transition={{ delay: delay + 0.3, duration: 0.4 }}
                    />
                    <motion.rect
                      x={x1}
                      y={y1}
                      width={x2 - x1}
                      height={y2 - y1}
                      fill="none"
                      stroke={color}
                      strokeWidth={imgW * 0.0025}
                      initial={{ pathLength: 0, opacity: 0 }}
                      animate={{ pathLength: 1, opacity: 1 }}
                      transition={{ delay, duration: 0.35 }}
                    />
                    <motion.g initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: delay + 0.15 }}>
                      <rect x={x1} y={y1 - imgH * 0.032} width={imgW * 0.12} height={imgH * 0.028} fill={`${color}25`} stroke={color} strokeWidth={1} />
                      <text
                        x={x1 + imgW * 0.004}
                        y={y1 - imgH * 0.012}
                        fill={color}
                        fontSize={imgH * 0.018}
                        fontFamily="monospace"
                        fontWeight="bold"
                      >
                        {seat.seat_id} {seat.status === 'occluded' ? STATUS_LABEL[seat.status] : `${Math.round(seat.confidence * 100)}%`}
                      </text>
                    </motion.g>
                  </g>
                )
              })}
            </svg>
          )}

          {/* Completion card */}
          <AnimatePresence>
            {stage === 'complete' && result && (
              <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                className="absolute inset-0 z-40 flex items-center justify-center"
                style={{ background: 'rgba(5,8,7,0.55)' }}
              >
                <div className="flex flex-col items-center text-center px-6">
                  <CheckCircle2 size={54} style={{ color: result.coverage_pct >= 80 ? STATUS_COLOR.calm : result.coverage_pct >= 50 ? STATUS_COLOR.watch : STATUS_COLOR.critical }} />
                  <div
                    className="mt-3 text-sm font-bold mono px-4 py-1.5 rounded-lg border"
                    style={{
                      color: result.coverage_pct >= 80 ? STATUS_COLOR.calm : result.coverage_pct >= 50 ? STATUS_COLOR.watch : STATUS_COLOR.critical,
                      borderColor: `${result.coverage_pct >= 80 ? STATUS_COLOR.calm : result.coverage_pct >= 50 ? STATUS_COLOR.watch : STATUS_COLOR.critical}50`,
                    }}
                  >
                    SETUP SCAN COMPLETE — {result.coverage_pct}% COVERAGE
                  </div>
                  <div className="mt-3 flex gap-4 text-[11px] mono text-white/60">
                    <span style={{ color: STATUS_COLOR.calm }}>{result.visible_count} visible</span>
                    <span style={{ color: STATUS_COLOR.watch }}>{result.partial_count} partial</span>
                    <span style={{ color: STATUS_COLOR.critical }}>{result.occluded_count} occluded</span>
                  </div>
                  <p className="mt-2 text-[10px] text-white/35 max-w-sm">
                    every box above is a real detection from this camera's own {result.duration_seconds}s scan window — not a simulation.
                  </p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {error && (
            <div className="absolute inset-0 z-40 flex items-center justify-center bg-black/70">
              <p className="text-xs text-critical px-6 text-center">{error}</p>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between px-5 py-3.5 border-t border-white/8">
          <p className="text-[10px] mono text-white/35">
            {stage === 'complete' ? 'scan reflects real detections during the window above' : 'scanning real footage from this camera…'}
          </p>
          {(stage === 'complete' || error) && (
            <button
              onClick={() => {
                startedRef.current = false
                setFrozenFrame(null)
                runScan()
              }}
              className="flex items-center gap-1.5 text-[11px] mono px-3 py-1.5 rounded-lg border border-white/15 text-white/70 hover:border-white/30"
            >
              <RotateCcw size={12} /> scan again
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
