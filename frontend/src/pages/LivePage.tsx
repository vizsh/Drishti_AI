import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { Video, VideoOff, X } from 'lucide-react'
import { LiveFeed } from '../components/LiveFeed'
import { useLive } from '../state/LiveContext'

interface CameraConfig {
  camera_id: string
  is_simulated: boolean
  is_primary: boolean
  seats: string[]
  streams_live_feed: boolean
}

export function LivePage() {
  const { feedImage, detectorFinetuned, lightingEnhanced } = useLive()
  const [cameras, setCameras] = useState<CameraConfig[]>([])
  const [focusedId, setFocusedId] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/cameras').then((r) => r.json()).then((d) => setCameras(d.cameras ?? []))
  }, [])

  // Snapshot throttling for unfocused tiles (Problem 3): this project has
  // only one real camera video feed, so there's a single physical stream
  // arriving over the WebSocket regardless of focus state — the backend
  // doesn't yet support per-camera subscription teardown. What IS real here:
  // grid tiles only repaint every 4s from that stream instead of on every
  // frame, and only the focused tile renders continuously. That's a genuine
  // render-cost reduction, just not a network-level one — worth being
  // precise about rather than implying a capability that doesn't exist yet.
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

  if (focused) {
    return (
      <div>
        <button
          onClick={() => setFocusedId(null)}
          className="flex items-center gap-1.5 text-xs mono px-3 py-1.5 rounded-lg border border-white/12 mb-4 hover:border-white/30"
        >
          <X size={13} /> close live view — back to camera grid
        </button>
        <LiveFeed feedImage={feedImage} detectorFinetuned={detectorFinetuned} lightingEnhanced={lightingEnhanced} />
        <p className="text-[10px] mono text-white/30 mt-3">covers: {focused.seats.map((s) => s.toUpperCase()).join(', ') || 'no seats calibrated'}</p>
      </div>
    )
  }

  if (cameras.length === 0) {
    return <div className="text-sm mono text-white/30 py-16 text-center">no cameras configured</div>
  }

  return (
    <div>
      <h2 className="text-sm font-bold uppercase tracking-wide mb-3">Camera grid</h2>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {cameras.map((cam) => (
          <CameraTile key={cam.camera_id} cam={cam} snapshot={snapshot} onOpen={() => cam.streams_live_feed && setFocusedId(cam.camera_id)} />
        ))}
      </div>
    </div>
  )
}

function CameraTile({ cam, snapshot, onOpen }: { cam: CameraConfig; snapshot: string | null; onOpen: () => void }) {
  const clickable = cam.streams_live_feed
  return (
    <motion.div
      whileHover={clickable ? { scale: 1.02 } : {}}
      onClick={onOpen}
      className={`rounded-2xl border border-white/8 overflow-hidden ${clickable ? 'cursor-pointer' : ''}`}
    >
      <div className="relative" style={{ aspectRatio: '16/10', background: '#000' }}>
        {clickable && snapshot ? (
          <img src={snapshot} className="w-full h-full object-cover opacity-90" />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            {clickable ? <Video size={20} className="text-white/20" /> : <VideoOff size={20} className="text-white/20" />}
          </div>
        )}
        <div className="absolute top-2 left-2 flex items-center gap-1.5 px-2 py-1 rounded-md text-[9px] mono bg-black/60">
          {cam.is_simulated ? 'SIMULATED' : 'LIVE'}
        </div>
        {clickable && (
          <div className="absolute bottom-2 right-2 text-[9px] mono px-2 py-1 rounded-md bg-black/60 text-white/60">click to open</div>
        )}
      </div>
      <div className="p-3">
        <div className="text-xs font-bold mb-1">{cam.camera_id}</div>
        <div className="text-[10px] mono text-white/40">
          {clickable ? 'streaming' : 'fusion-only · no visual feed'} · {cam.seats.length} seat{cam.seats.length === 1 ? '' : 's'}
        </div>
      </div>
    </motion.div>
  )
}
