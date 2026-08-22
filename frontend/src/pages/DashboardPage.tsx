import { useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { AlertTriangle, CameraOff, ShieldCheck, Video, VideoOff, Unplug } from 'lucide-react'
import { useLive } from '../state/LiveContext'
import { useHallScope, type CameraInfo } from '../state/useHallScope'
import { severityForCamera } from '../lib/cameraSeverity'
import { shortAlertSummary } from '../lib/shortSummary'
import { EmptyState } from '../components/EmptyState'
import type { AlertItem } from '../types'

const BORDER_COLOR = { calm: '#ffffff1a', watch: '#ffb64870', critical: '#ff5a3690' } as const
const STRIP_COLOR = { calm: '', watch: '#ffb648', critical: '#ff5a36' } as const

// Dashboard (2026-08-22): the presentation-facing front door — every
// configured camera actually visible at once, in one dense grid, with the
// one thing that matters to someone watching footage surfaced directly on
// the tile (what's suspicious, right now, in plain language) instead of
// requiring a click to find out there's nothing there. Deliberately does
// NOT duplicate the investigation view — clicking a tile goes straight to
// the same /seat/:seatId page (ActionDrawer, evidence, dispatch/resolve)
// every other alert path already uses, so there's exactly one place that
// logic lives.
export function DashboardPage() {
  const navigate = useNavigate()
  const { seats, alerts, feedImages, setStreamMode } = useLive()
  const { cameras, halls } = useHallScope()

  // Every camera that has its own worker streams a low-rate background
  // thumbnail while this page is open — the fix for "only one of them is
  // working," not a cosmetic grid over blank tiles.
  useEffect(() => {
    for (const cam of cameras) {
      if (cam.has_own_worker) setStreamMode(cam.camera_id, 'background')
    }
  }, [cameras, setStreamMode])

  // Most recent alert per seat, so a camera's tile can show the actual
  // real explanation text ("seat_5 — cell phone detected...") rather than
  // a generic "warning" — pulled from the same live alert feed every other
  // page reads, not a second data path.
  const latestAlertBySeat = useMemo(() => {
    const map = new Map<string, AlertItem>()
    for (const a of alerts) {
      if (a.kind !== 'alert') continue
      const existing = map.get(a.seatId)
      if (!existing || a.timestamp > existing.timestamp) map.set(a.seatId, a)
    }
    return map
  }, [alerts])

  function openCamera(cam: CameraInfo) {
    const sev = severityForCamera(cam, seats)
    const targetSeat = sev.worstSeat ?? cam.seats[0]
    if (targetSeat) navigate(`/seat/${targetSeat}`)
  }

  if (cameras.length === 0) {
    return (
      <EmptyState
        icon={CameraOff}
        title="No cameras configured for your access scope"
        body="Either no cameras have been added to this deployment yet, or none are assigned to a hall you have access to."
      />
    )
  }

  return (
    <div>
      <h1 className="text-lg font-bold mb-1">Dashboard</h1>
      <p className="text-xs mono text-white/35 mb-6">
        every configured camera, at a glance · click a tile for the full investigation view
      </p>
      {halls.map((hall) => {
        const hallCameras = cameras.filter((c) => c.hall === hall)
        if (hallCameras.length === 0) return null
        return (
          <div key={hall} className="mb-8">
            <h2 className="text-sm font-bold uppercase tracking-wide mb-3 text-white/60">{hall}</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4">
              {hallCameras.map((cam) => (
                <DashboardTile
                  key={cam.camera_id}
                  cam={cam}
                  snapshot={feedImages[cam.camera_id] ?? null}
                  severity={severityForCamera(cam, seats)}
                  latestAlert={cam.seats.map((s) => latestAlertBySeat.get(s)).find(Boolean) ?? null}
                  onOpen={() => openCamera(cam)}
                />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function DashboardTile({
  cam,
  snapshot,
  severity,
  latestAlert,
  onOpen,
}: {
  cam: CameraInfo
  snapshot: string | null
  severity: { level: 'calm' | 'watch' | 'critical'; count: number; worstSeat: string | null }
  latestAlert: AlertItem | null
  onOpen: () => void
}) {
  const clickable = !cam.disconnected && cam.seats.length > 0
  // Two distinct reasons a tile can be non-calm: a formal alert fired
  // (real explanation text available), or risk is elevated (e.g. a
  // gesture in progress) without one having fired yet — the strip text
  // must agree with the badge either way, not silently say "all calm"
  // under a nonzero count.
  const hasAlert = !cam.disconnected && severity.level !== 'calm' && !!latestAlert
  const elevatedNoAlert = !cam.disconnected && severity.level !== 'calm' && !latestAlert

  return (
    <motion.div
      whileHover={clickable ? { scale: 1.02 } : {}}
      onClick={clickable ? onOpen : undefined}
      animate={!cam.disconnected && severity.level === 'critical' ? { borderColor: [BORDER_COLOR.critical, '#ff5a36ff', BORDER_COLOR.critical] } : {}}
      transition={{ duration: 1.6, repeat: !cam.disconnected && severity.level === 'critical' ? Infinity : 0 }}
      className={`rounded-2xl border overflow-hidden ${clickable ? 'cursor-pointer' : ''}`}
      style={{ borderColor: cam.disconnected ? '#ffffff14' : BORDER_COLOR[severity.level] }}
    >
      <div className="relative" style={{ aspectRatio: '16/10', background: '#000' }}>
        {!cam.disconnected && snapshot ? (
          <img src={snapshot} className="w-full h-full object-cover opacity-90" />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            {cam.disconnected ? (
              <Unplug size={20} className="text-white/25" />
            ) : cam.streams_live_feed ? (
              <Video size={20} className="text-white/20" />
            ) : (
              <VideoOff size={20} className="text-white/20" />
            )}
          </div>
        )}
        <div className="absolute top-2 left-2 flex items-center gap-1.5">
          <span className="text-[9px] mono uppercase tracking-wide px-2 py-0.5 rounded-full bg-black/50 text-white/70">
            {cam.disconnected ? 'disconnected' : cam.is_simulated ? 'simulated' : 'live'}
          </span>
        </div>
        {!cam.disconnected && severity.count > 0 && (
          <div className="absolute top-2 right-2 flex items-center gap-1 text-[9px] mono px-2 py-0.5 rounded-full" style={{ background: `${STRIP_COLOR[severity.level]}30`, color: STRIP_COLOR[severity.level] }}>
            <AlertTriangle size={9} /> {severity.count}
          </div>
        )}
      </div>

      {/* The one thing that actually matters to someone watching this
          tile: is there something suspicious, and what is it — plain
          language, pulled from the real alert, right on the block. */}
      {hasAlert ? (
        <div className="px-3 py-2.5 border-t" style={{ borderColor: `${STRIP_COLOR[severity.level]}40`, background: `${STRIP_COLOR[severity.level]}12` }}>
          <div className="text-[11px] font-bold mb-0.5" style={{ color: STRIP_COLOR[severity.level] }}>
            {latestAlert!.seatId.toUpperCase()} — {latestAlert!.needsVerification ? 'possible activity, please verify' : 'suspicious activity'}
          </div>
          <p className="text-[10px] text-white/70 leading-snug line-clamp-2">{shortAlertSummary(latestAlert!.explanation)}</p>
        </div>
      ) : elevatedNoAlert ? (
        <div className="px-3 py-2.5 border-t" style={{ borderColor: `${STRIP_COLOR[severity.level]}40`, background: `${STRIP_COLOR[severity.level]}12` }}>
          <div className="text-[11px] font-bold" style={{ color: STRIP_COLOR[severity.level] }}>
            {severity.worstSeat?.toUpperCase()} — elevated, watching
          </div>
          <p className="text-[10px] text-white/60 leading-snug">no confirmed incident yet — risk is above baseline</p>
        </div>
      ) : (
        <div className="px-3 py-2.5 border-t border-white/6">
          <div className="flex items-center gap-1.5 text-[11px] text-white/60">
            <ShieldCheck size={12} className="text-calm/70" /> all calm
          </div>
        </div>
      )}

      <div className="px-3 pb-2.5 pt-1">
        <div className="text-xs font-bold mb-0.5">{cam.camera_id}</div>
        <div className="text-[10px] mono text-white/40">
          {cam.disconnected
            ? 'source disconnected'
            : cam.seats.length > 0
              ? `${cam.seats.length} seat${cam.seats.length === 1 ? '' : 's'} covered`
              : 'fusion-only · no seats of its own'}
        </div>
      </div>
    </motion.div>
  )
}
