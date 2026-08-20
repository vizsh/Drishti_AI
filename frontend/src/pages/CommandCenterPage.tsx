import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Video, VideoOff, X, AlertTriangle, CameraOff } from 'lucide-react'
import { LiveFeed } from '../components/LiveFeed'
import { Badge } from '../components/Badge'
import { ValueStats } from '../components/ValueStats'
import { EmptyState } from '../components/EmptyState'
import { useLive } from '../state/LiveContext'
import { useHallScope, type CameraInfo } from '../state/useHallScope'
import { riskLevel, type StatusLevel } from '../lib/colors'

/**
 * Phase 2 — Command Center: the default landing view after login. A real
 * analyst wall (Technology Challenge #8, scale): every configured camera
 * the logged-in user's role can see, grouped by hall, each tile a
 * lightweight snapshot + status border — never full video for more than
 * one tile at a time (Performance Note, applies everywhere).
 */
export function CommandCenterPage() {
  const navigate = useNavigate()
  const { seats, feedImage, detectorFinetuned, lightingEnhanced } = useLive()
  const { cameras, halls } = useHallScope()
  const [focusedId, setFocusedId] = useState<string | null>(null)

  // Snapshot throttling (Problem 3 / Performance Note): this project has
  // only one real camera video feed, so there's a single physical stream
  // arriving over the WebSocket regardless of focus state — the backend
  // doesn't yet support per-camera subscription teardown. What IS real
  // here: grid tiles only repaint every 4s from that stream instead of on
  // every frame, and only the focused tile renders continuously. A genuine
  // render-cost reduction, not a network-level one — worth being precise
  // about rather than implying a capability that doesn't exist yet.
  const [snapshot, setSnapshot] = useState<string | null>(null)
  const lastSnapshotAt = useRef(0)
  useEffect(() => {
    if (!feedImage) return
    const now = Date.now()
    if (now - lastSnapshotAt.current > 4000) {
      lastSnapshotAt.current = now
      setSnapshot(feedImage)
    }
  }, [feedImage])

  const focused = cameras.find((c) => c.camera_id === focusedId)

  function severityFor(cam: CameraInfo): { level: StatusLevel; count: number; worstSeat: string | null } {
    let level: StatusLevel = 'calm'
    let count = 0
    let worstSeat: string | null = null
    for (const seatId of cam.seats) {
      const s = seats[seatId]
      if (!s?.calibrated) continue
      const l = riskLevel(s.risk)
      if (l === 'critical') {
        level = 'critical'
        count += 1
        worstSeat = seatId
      } else if (l === 'watch' && level !== 'critical') {
        level = 'watch'
        count += 1
        if (!worstSeat) worstSeat = seatId
      }
    }
    return { level, count, worstSeat }
  }

  function openTile(cam: CameraInfo) {
    const sev = severityFor(cam)
    if (sev.level === 'critical' && sev.worstSeat) {
      // Flagged tile -> straight into the investigation view (Phase 3).
      navigate(`/seat/${sev.worstSeat}`)
    } else if (cam.streams_live_feed) {
      // Calm tile -> lightweight single-feed live view, this page only.
      setFocusedId(cam.camera_id)
    }
  }

  if (focused) {
    return (
      <div>
        <button
          onClick={() => setFocusedId(null)}
          className="flex items-center gap-1.5 text-xs mono px-3 py-1.5 rounded-lg border border-white/12 mb-4 hover:border-white/30"
        >
          <X size={13} /> close live view — back to command center
        </button>
        <LiveFeed feedImage={feedImage} detectorFinetuned={detectorFinetuned} lightingEnhanced={lightingEnhanced} />
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
                <CameraTile key={cam.camera_id} cam={cam} snapshot={snapshot} severity={severityFor(cam)} onOpen={() => openTile(cam)} />
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
}: {
  cam: CameraInfo
  snapshot: string | null
  severity: { level: StatusLevel; count: number }
  onOpen: () => void
}) {
  const clickable = cam.streams_live_feed || severity.level === 'critical'
  return (
    <motion.div
      whileHover={clickable ? { scale: 1.02 } : {}}
      onClick={clickable ? onOpen : undefined}
      animate={severity.level === 'critical' ? { borderColor: [BORDER_COLOR.critical, '#ff5a36ff', BORDER_COLOR.critical] } : {}}
      transition={{ duration: 1.6, repeat: severity.level === 'critical' ? Infinity : 0 }}
      className={`rounded-2xl border overflow-hidden ${clickable ? 'cursor-pointer' : ''} ${GLOW[severity.level]}`}
      style={{ borderColor: BORDER_COLOR[severity.level] }}
    >
      <div className="relative" style={{ aspectRatio: '16/10', background: '#000' }}>
        {cam.streams_live_feed && snapshot ? (
          <img src={snapshot} className="w-full h-full object-cover opacity-90" />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            {cam.streams_live_feed ? <Video size={20} className="text-white/20" /> : <VideoOff size={20} className="text-white/20" />}
          </div>
        )}
        <div className="absolute top-2 left-2">
          <Badge tone="neutral">{cam.is_simulated ? 'SIMULATED' : 'LIVE'}</Badge>
        </div>
        {severity.level !== 'calm' && (
          <div className="absolute top-2 right-2">
            <Badge tone={severity.level}>
              <AlertTriangle size={10} /> {severity.count}
            </Badge>
          </div>
        )}
      </div>
      <div className="p-3">
        <div className="text-xs font-bold mb-1">{cam.camera_id}</div>
        <div className="text-[10px] mono text-white/40">
          {cam.streams_live_feed ? 'streaming' : 'fusion-only · no visual feed'} · {cam.seats.length} seat{cam.seats.length === 1 ? '' : 's'}
        </div>
      </div>
    </motion.div>
  )
}
