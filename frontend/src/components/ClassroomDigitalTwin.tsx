import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { Radar, ShieldCheck, Smartphone } from 'lucide-react'
import { useLive } from '../state/LiveContext'
import { STATUS_COLOR, riskLevel } from '../lib/colors'
import type { AlertItem } from '../types'

const HUD_CYAN = '#5ad1ff'

interface Layout {
  camera_id: string
  image_width: number
  image_height: number
  seat_boxes: Record<string, [number, number, number, number]>
}

// Product request (2026-08-22): "a digital twin of the classroom while
// sensing the surrounding, as part of the pre-processing part of the
// CCTVs." RoomScanOverlay already proved this exact wireframe language
// (real calibration-derived boxes, staggered reveal, HUD chrome) works —
// this is the persistent, always-on version of it: instead of a one-shot
// animated scan, it fetches this camera's real seat geometry once (GET
// /api/setup/cameras/{id}/layout, the same SeatCalibration.project_inverse
// math the scan uses) and then drives every box's color and label off the
// SAME live seat state every other page reads — nothing here is simulated
// or re-derived separately. Escalation follows the same calm-by-default
// rule as Live Monitor/Examination Hall: a seat's box only leaves calm
// once a real, notify-worthy alert exists for it.
export function ClassroomDigitalTwin({ cameraId }: { cameraId: string }) {
  const { seats, alerts, feedImages, setStreamMode } = useLive()
  const [layout, setLayout] = useState<Layout | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sweep, setSweep] = useState(0)

  useEffect(() => {
    setLayout(null)
    setError(null)
    fetch(`/api/setup/cameras/${cameraId}/layout`)
      .then((r) => {
        if (!r.ok) throw new Error('no calibration data for this camera')
        return r.json()
      })
      .then(setLayout)
      .catch((e) => setError(e instanceof Error ? e.message : 'failed to load layout'))
  }, [cameraId])

  useEffect(() => {
    setStreamMode(cameraId, 'focused')
    return () => {
      setStreamMode(cameraId, 'background')
    }
  }, [cameraId, setStreamMode])

  // A slow vertical sweep, purely presentational — the "sensing" feel a
  // static wireframe doesn't convey, same idea as a radar or LIDAR scan
  // display. Doesn't gate or delay anything real underneath it.
  useEffect(() => {
    let raf: number
    const start = Date.now()
    function tick() {
      const t = ((Date.now() - start) / 4000) % 1
      setSweep(t)
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [])

  const latestAlertBySeat = useMemo(() => {
    const map = new Map<string, AlertItem>()
    for (const a of alerts) {
      if (a.kind !== 'alert' || a.notify === false) continue
      const existing = map.get(a.seatId)
      if (!existing || a.timestamp > existing.timestamp) map.set(a.seatId, a)
    }
    return map
  }, [alerts])

  if (error) {
    return (
      <div className="rounded-2xl border border-white/8 p-8 text-center">
        <p className="text-xs text-white/35 mono">{error}</p>
      </div>
    )
  }
  if (!layout) {
    return (
      <div className="rounded-2xl border border-white/8 p-8 text-center">
        <p className="text-xs text-white/35 mono">sensing classroom geometry…</p>
      </div>
    )
  }

  const imgW = layout.image_width
  const imgH = layout.image_height
  const camIconX = imgW / 2
  const camIconY = imgH * 0.06
  const seatIds = Object.keys(layout.seat_boxes)
  const calibratedCount = seatIds.filter((id) => seats[id]?.calibrated).length
  const alertedCount = seatIds.filter((id) => latestAlertBySeat.has(id)).length

  return (
    <div className="rounded-2xl border border-white/8 overflow-hidden" style={{ background: '#0a0a0d' }}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/8">
        <div className="flex items-center gap-2">
          <Radar size={14} style={{ color: HUD_CYAN }} className="animate-pulse" />
          <span className="text-xs font-bold mono uppercase tracking-wide" style={{ color: HUD_CYAN }}>
            digital twin — {layout.camera_id}
          </span>
        </div>
        <div className="flex items-center gap-3 text-[10px] mono text-white/40">
          <span>{seatIds.length} sensed</span>
          <span>{calibratedCount} calibrated</span>
          {alertedCount > 0 ? (
            <span style={{ color: STATUS_COLOR.critical }}>{alertedCount} flagged</span>
          ) : (
            <span style={{ color: STATUS_COLOR.calm }} className="flex items-center gap-1">
              <ShieldCheck size={11} /> all calm
            </span>
          )}
        </div>
      </div>

      <div className="relative" style={{ aspectRatio: `${imgW}/${imgH}`, background: '#000' }}>
        {feedImages[cameraId] && (
          <img src={feedImages[cameraId]} className="absolute inset-0 w-full h-full object-cover opacity-25" />
        )}
        <div
          className="absolute inset-0 pointer-events-none z-20"
          style={{ boxShadow: 'inset 0 0 80px 26px rgba(0,0,0,0.7)' }}
        />
        {[
          { top: 8, left: 8, borderRight: 0, borderBottom: 0 },
          { top: 8, right: 8, borderLeft: 0, borderBottom: 0 },
          { bottom: 8, left: 8, borderRight: 0, borderTop: 0 },
          { bottom: 8, right: 8, borderLeft: 0, borderTop: 0 },
        ].map((pos, i) => (
          <div key={i} className="absolute w-5 h-5 border-2 z-20 pointer-events-none" style={{ ...pos, borderColor: `${HUD_CYAN}80` }} />
        ))}

        <svg viewBox={`0 0 ${imgW} ${imgH}`} className="absolute inset-0 w-full h-full z-10">
          {/* faint floor grid — purely presentational, the "digital twin" cue */}
          {Array.from({ length: 6 }).map((_, i) => (
            <line key={`v${i}`} x1={(imgW / 6) * i} y1={0} x2={(imgW / 6) * i} y2={imgH} stroke={HUD_CYAN} strokeOpacity={0.06} strokeWidth={1} />
          ))}
          {Array.from({ length: 4 }).map((_, i) => (
            <line key={`h${i}`} x1={0} y1={(imgH / 4) * i} x2={imgW} y2={(imgH / 4) * i} stroke={HUD_CYAN} strokeOpacity={0.06} strokeWidth={1} />
          ))}
          {/* looping sensing sweep */}
          <motion.line
            x1={0}
            x2={imgW}
            y1={imgH * sweep}
            y2={imgH * sweep}
            stroke={HUD_CYAN}
            strokeWidth={imgH * 0.006}
            opacity={0.35}
          />

          <circle cx={camIconX} cy={camIconY} r={imgW * 0.012} fill={HUD_CYAN} opacity={0.9} />

          {seatIds.map((seatId) => {
            const [x1, y1, x2, y2] = layout.seat_boxes[seatId]
            const cx = (x1 + x2) / 2
            const cy = (y1 + y2) / 2
            const seat = seats[seatId]
            const alerted = latestAlertBySeat.has(seatId)
            const level = alerted && seat?.calibrated ? riskLevel(seat.risk) : 'calm'
            const color = STATUS_COLOR[level]
            const sensed = !!seat
            return (
              <g key={seatId} opacity={sensed ? 1 : 0.35}>
                <line x1={camIconX} y1={camIconY} x2={cx} y2={cy} stroke={color} strokeWidth={imgW * 0.0012} strokeDasharray="6 5" opacity={alerted ? 0.6 : 0.25} />
                <rect
                  x={x1}
                  y={y1}
                  width={x2 - x1}
                  height={y2 - y1}
                  fill="none"
                  stroke={color}
                  strokeWidth={imgW * (alerted ? 0.0028 : 0.0018)}
                />
                <rect x={x1} y={y1 - imgH * 0.03} width={imgW * 0.1} height={imgH * 0.026} fill={`${color}25`} stroke={color} strokeWidth={1} />
                <text x={x1 + imgW * 0.004} y={y1 - imgH * 0.011} fill={color} fontSize={imgH * 0.017} fontFamily="monospace" fontWeight="bold">
                  {seatId.replace('seat_', 'S')}{!sensed ? ' idle' : alerted ? ' !' : ''}
                </text>
              </g>
            )
          })}
        </svg>

        {/* real object-detection callouts, drawn above the SVG layer */}
        {seatIds.map((seatId) => {
          const objectLabel = latestAlertBySeat.get(seatId)?.objectLabel
          if (!objectLabel) return null
          const [x1, y1, x2] = layout.seat_boxes[seatId]
          const leftPct = ((x1 + x2) / 2 / imgW) * 100
          const topPct = (y1 / imgH) * 100
          return (
            <div
              key={seatId}
              className="absolute z-30 flex items-center gap-1 text-[9px] mono px-1.5 py-0.5 rounded"
              style={{ left: `${leftPct}%`, top: `${Math.max(0, topPct - 6)}%`, transform: 'translateX(-50%)', background: '#00000090', color: STATUS_COLOR.critical, border: `1px solid ${STATUS_COLOR.critical}60` }}
            >
              <Smartphone size={9} /> {objectLabel}
            </div>
          )
        })}
      </div>

      <div className="px-4 py-2.5 border-t border-white/8">
        <p className="text-[10px] mono text-white/30">
          every box is this camera's real calibrated seat position — color and labels follow the same live risk state as Live Monitor, not a simulation.
        </p>
      </div>
    </div>
  )
}
