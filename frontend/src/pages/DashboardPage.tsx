import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { AlertTriangle, CameraOff, ShieldCheck, Video, VideoOff, Unplug, Plug } from 'lucide-react'
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
  const { cameras, halls, refreshCameras } = useHallScope()
  const [toggling, setToggling] = useState<string | null>(null)

  async function toggleConnection(cam: CameraInfo) {
    setToggling(cam.camera_id)
    try {
      const action = cam.disconnected ? 'reconnect' : 'disconnect'
      await fetch(`/api/setup/cameras/${cam.camera_id}/${action}`, { method: 'POST' })
      await refreshCameras()
    } finally {
      setToggling(null)
    }
  }

  // Every camera that has its own worker streams a low-rate background
  // thumbnail while this page is open — the fix for "only one of them is
  // working," not a cosmetic grid over blank tiles.
  useEffect(() => {
    for (const cam of cameras) {
      if (cam.has_own_worker) setStreamMode(cam.camera_id, 'background')
    }
  }, [cameras, setStreamMode])

  // Most recent NOTIFY-WORTHY alert per seat, so a camera's tile can show
  // the actual real explanation text ("seat_5 — cell phone detected...")
  // rather than a generic "warning" — pulled from the same live alert feed
  // every other page reads, not a second data path. Deliberately excludes
  // notify:false alerts (e.g. a needs_verification hit still on its first
  // occurrence) — a tile is not supposed to react to every fluctuation in
  // a student's ordinary movement, only to something that actually cleared
  // the same review bar the Alert Inbox uses.
  const latestAlertBySeat = useMemo(() => {
    const map = new Map<string, AlertItem>()
    for (const a of alerts) {
      if (a.kind !== 'alert' || a.notify === false) continue
      const existing = map.get(a.seatId)
      if (!existing || a.timestamp > existing.timestamp) map.set(a.seatId, a)
    }
    return map
  }, [alerts])

  function openCamera(cam: CameraInfo) {
    // Product audit §7.2: a tile used to jump straight past the camera
    // entirely to one seat's telemetry, with no way to actually watch the
    // footage. Now it opens the camera's own detail view (real video next
    // to the same analytics) — a specific seat is still one click away
    // from there via the alert feed.
    navigate(`/camera/${cam.camera_id}`)
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
      <h1 className="text-lg font-bold mb-1">Live Monitor</h1>
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
                  onToggleConnection={() => toggleConnection(cam)}
                  toggling={toggling === cam.camera_id}
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
  onToggleConnection,
  toggling,
}: {
  cam: CameraInfo
  snapshot: string | null
  severity: { level: 'calm' | 'watch' | 'critical'; count: number; worstSeat: string | null }
  latestAlert: AlertItem | null
  onOpen: () => void
  onToggleConnection: () => void
  toggling: boolean
}) {
  const clickable = !cam.disconnected && cam.seats.length > 0
  // A tile only leaves "calm" when a real, notify-worthy alert exists —
  // not on every fluctuation of a student's raw risk score. Ordinary
  // movement (stretching, glancing around) constantly crosses the
  // watch/critical z-score bands and used to visibly flip the tile's color
  // on every such crossing; that's exactly the "too dynamic" behaviour
  // this was built to stop. Only something that already cleared the same
  // review bar the Alert Inbox uses gets to change what this tile shows.
  const hasAlert = !cam.disconnected && !!latestAlert
  const level = hasAlert ? severity.level : 'calm'

  return (
    <motion.div
      whileHover={clickable ? { scale: 1.02 } : {}}
      onClick={clickable ? onOpen : undefined}
      animate={hasAlert && level === 'critical' ? { borderColor: [BORDER_COLOR.critical, '#ff5a36ff', BORDER_COLOR.critical] } : {}}
      transition={{ duration: 1.6, repeat: hasAlert && level === 'critical' ? Infinity : 0 }}
      className={`rounded-2xl border overflow-hidden relative ${clickable ? 'cursor-pointer' : ''}`}
      style={{ borderColor: cam.disconnected ? '#ffffff14' : BORDER_COLOR[level] }}
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
        {!cam.disconnected && severity.count > 0 && hasAlert && (
          <div className="absolute top-2 right-2 flex items-center gap-1 text-[9px] mono px-2 py-0.5 rounded-full" style={{ background: `${STRIP_COLOR[level]}30`, color: STRIP_COLOR[level] }}>
            <AlertTriangle size={9} /> {severity.count}
          </div>
        )}
        <button
          onClick={(e) => { e.stopPropagation(); onToggleConnection() }}
          disabled={toggling}
          title={cam.disconnected ? 'reconnect this source' : 'disconnect this source'}
          className="absolute bottom-2 right-2 flex items-center gap-1 text-[9px] mono uppercase tracking-wide px-2 py-1 rounded-full bg-black/55 hover:bg-black/75 text-white/70 hover:text-white transition-colors disabled:opacity-50"
        >
          {cam.disconnected ? <Plug size={10} /> : <Unplug size={10} />}
          {toggling ? '…' : cam.disconnected ? 'reconnect' : 'disconnect'}
        </button>
      </div>

      {/* The one thing that actually matters to someone watching this
          tile: is there something suspicious, and what is it — plain
          language, pulled from the real alert, right on the block. */}
      {hasAlert ? (
        <div className="px-3 py-2.5 border-t" style={{ borderColor: `${STRIP_COLOR[level]}40`, background: `${STRIP_COLOR[level]}12` }}>
          <div className="text-[11px] font-bold mb-0.5" style={{ color: STRIP_COLOR[level] }}>
            {latestAlert!.seatId.toUpperCase()} — {latestAlert!.needsVerification ? 'possible activity, please verify' : 'suspicious activity'}
          </div>
          <p className="text-[10px] text-white/70 leading-snug line-clamp-2">{shortAlertSummary(latestAlert!.explanation)}</p>
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
