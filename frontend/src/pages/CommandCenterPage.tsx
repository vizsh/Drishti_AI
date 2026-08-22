import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Video, VideoOff, X, AlertTriangle, CameraOff, Unplug, Plug, Loader2 } from 'lucide-react'
import { LiveFeed } from '../components/LiveFeed'
import { Badge } from '../components/Badge'
import { ValueStats } from '../components/ValueStats'
import { EmptyState } from '../components/EmptyState'
import { useLive } from '../state/LiveContext'
import { useHallScope, type CameraInfo } from '../state/useHallScope'
import { type StatusLevel } from '../lib/colors'
import { severityForCamera } from '../lib/cameraSeverity'

/**
 * Phase 2 — Command Center: the default landing view after login. A real
 * analyst wall (Technology Challenge #8, scale): every configured camera
 * the logged-in user's role can see, grouped by hall, each tile a
 * lightweight snapshot + status border — never full video for more than
 * one tile at a time (Performance Note, applies everywhere).
 */
export function CommandCenterPage() {
  const navigate = useNavigate()
  const { seats, feedImages, detectorFinetuned, lightingEnhanced, setStreamMode } = useLive()
  const { cameras, halls, refreshCameras } = useHallScope()
  const [focusedId, setFocusedId] = useState<string | null>(null)
  const [togglingId, setTogglingId] = useState<string | null>(null)

  async function toggleConnection(cam: CameraInfo) {
    setTogglingId(cam.camera_id)
    try {
      const action = cam.disconnected ? 'reconnect' : 'disconnect'
      await fetch(`/api/setup/cameras/${cam.camera_id}/${action}`, { method: 'POST' })
      await refreshCameras()
    } finally {
      setTogglingId(null)
    }
  }

  // Dashboard grid fix (2026-08-22): every camera with its own worker now
  // streams a low-rate "background" thumbnail on its own — this page just
  // needs to ask for it once per camera in scope, instead of relying on a
  // single hardcoded primary. Grid tiles read straight from feedImages
  // (already backend-throttled); only the opened single-feed view below
  // asks for "focused" (full rate), and drops back to "background" on close.
  useEffect(() => {
    for (const cam of cameras) {
      if (cam.has_own_worker) setStreamMode(cam.camera_id, 'background')
    }
  }, [cameras, setStreamMode])

  const focused = cameras.find((c) => c.camera_id === focusedId)

  function openTile(cam: CameraInfo) {
    const sev = severityForCamera(cam, seats)
    if (sev.level === 'critical' && sev.worstSeat) {
      // Flagged tile -> straight into the investigation view (Phase 3).
      navigate(`/seat/${sev.worstSeat}`)
    } else if (cam.streams_live_feed) {
      // Calm tile -> lightweight single-feed live view, this page only.
      setFocusedId(cam.camera_id)
      setStreamMode(cam.camera_id, 'focused')
    }
  }

  function closeFocused() {
    if (focused) setStreamMode(focused.camera_id, 'background')
    setFocusedId(null)
  }

  if (focused) {
    return (
      <div>
        <button
          onClick={closeFocused}
          className="flex items-center gap-1.5 text-xs mono px-3 py-1.5 rounded-lg border border-white/12 mb-4 hover:border-white/30"
        >
          <X size={13} /> close live view — back to command center
        </button>
        <LiveFeed feedImage={feedImages[focused.camera_id] ?? null} detectorFinetuned={detectorFinetuned} lightingEnhanced={lightingEnhanced} />
        <p className="text-[10px] mono text-white/30 mt-3">covers: {focused.seats.map((s) => s.toUpperCase()).join(', ') || 'no seats calibrated'}</p>
      </div>
    )
  }

  if (cameras.length === 0) {
    return (
      <EmptyState
        icon={CameraOff}
        title="No cameras configured for your access scope"
        body="Either no cameras have been added to this deployment yet, or none are assigned to a hall you have access to. Camera-to-hall assignment is set in config/deployment.json by whoever configured this deployment."
      />
    )
  }

  return (
    <div>
      <h1 className="text-lg font-bold mb-1">Command Center</h1>
      <p className="text-xs mono text-white/35 mb-4">
        {cameras.length} camera{cameras.length === 1 ? '' : 's'} · only the opened tile runs full live decode — everything else is a periodic snapshot
      </p>
      <ValueStats />
      {halls.map((hall) => {
        const hallCameras = cameras.filter((c) => c.hall === hall)
        if (hallCameras.length === 0) return null
        return (
          <div key={hall} className="mb-8">
            <h2 className="text-sm font-bold uppercase tracking-wide mb-3 text-white/60">{hall}</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              {hallCameras.map((cam) => (
                <CameraTile
                  key={cam.camera_id}
                  cam={cam}
                  snapshot={feedImages[cam.camera_id] ?? null}
                  severity={severityForCamera(cam, seats)}
                  onOpen={() => openTile(cam)}
                  onToggleConnection={() => toggleConnection(cam)}
                  toggling={togglingId === cam.camera_id}
                />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

const BORDER_COLOR: Record<StatusLevel, string> = { calm: '#ffffff1a', watch: '#ffb64870', critical: '#ff5a3690' }
const GLOW: Record<StatusLevel, string> = { calm: '', watch: 'shadow-[0_0_20px_-4px_#ffb64860]', critical: 'shadow-[0_0_28px_-2px_#ff5a3680]' }

function CameraTile({
  cam,
  snapshot,
  severity,
  onOpen,
  onToggleConnection,
  toggling,
}: {
  cam: CameraInfo
  snapshot: string | null
  severity: { level: StatusLevel; count: number }
  onOpen: () => void
  onToggleConnection: () => void
  toggling: boolean
}) {
  const clickable = !cam.disconnected && (cam.streams_live_feed || severity.level === 'critical')
  return (
    <motion.div
      whileHover={clickable ? { scale: 1.02 } : {}}
      onClick={clickable ? onOpen : undefined}
      animate={!cam.disconnected && severity.level === 'critical' ? { borderColor: [BORDER_COLOR.critical, '#ff5a36ff', BORDER_COLOR.critical] } : {}}
      transition={{ duration: 1.6, repeat: !cam.disconnected && severity.level === 'critical' ? Infinity : 0 }}
      className={`rounded-2xl border overflow-hidden ${clickable ? 'cursor-pointer' : ''} ${cam.disconnected ? 'opacity-50' : GLOW[severity.level]}`}
      style={{ borderColor: cam.disconnected ? '#ffffff14' : BORDER_COLOR[severity.level] }}
    >
      <div className="relative" style={{ aspectRatio: '16/10', background: '#000' }}>
        {!cam.disconnected && cam.streams_live_feed && snapshot ? (
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
        <div className="absolute top-2 left-2">
          <Badge tone="neutral">{cam.disconnected ? 'DISCONNECTED' : cam.is_simulated ? 'SIMULATED' : 'LIVE'}</Badge>
        </div>
        {!cam.disconnected && severity.level !== 'calm' && (
          <div className="absolute top-2 right-2">
            <Badge tone={severity.level}>
              <AlertTriangle size={10} /> {severity.count}
            </Badge>
          </div>
        )}
      </div>
      <div className="p-3">
        <div className="flex items-center justify-between gap-2 mb-1">
          <div className="text-xs font-bold">{cam.camera_id}</div>
          <button
            onClick={(e) => {
              e.stopPropagation()
              onToggleConnection()
            }}
            disabled={toggling}
            className="flex items-center gap-1 text-[9px] mono px-2 py-1 rounded-md border border-white/12 text-white/50 hover:border-white/30 hover:text-white/80 disabled:opacity-40 shrink-0"
            title={cam.disconnected ? 'Reconnect this camera' : 'Disconnect this camera (stops its pipeline; reversible)'}
          >
            {toggling ? <Loader2 size={10} className="animate-spin" /> : cam.disconnected ? <Plug size={10} /> : <Unplug size={10} />}
            {toggling ? '…' : cam.disconnected ? 'reconnect' : 'disconnect'}
          </button>
        </div>
        <div className="text-[10px] mono text-white/40">
          {cam.disconnected
            ? 'source disconnected — no pipeline running'
            : cam.streams_live_feed
              ? 'streaming'
              : 'fusion-only · no visual feed'}{' '}
          · {cam.seats.length} seat{cam.seats.length === 1 ? '' : 's'}
          {(cam.video_paths?.length ?? 0) > 1 && ` · ${cam.video_paths!.length}-video playlist`}
        </div>
      </div>
    </motion.div>
  )
}
