import { useMemo } from 'react'
import { Link2 } from 'lucide-react'
import { useHallScope } from '../state/useHallScope'
import { ClassroomDigitalTwin } from './ClassroomDigitalTwin'

// Feature: multi-camera fused twin. Each camera has its own independent
// pixel-space calibration (SeatCalibration) — there's no shared real-world
// floorplan coordinate system across cameras in this deployment, so
// honestly fusing them into one unified 2D map would mean fabricating
// coordinates that don't exist. What IS real and worth surfacing: which
// seats this hall's cameras redundantly cover (the same overlap
// LabSetupPage already computes to explain fusion pairing), shown once
// above every camera's own twin rendered side by side — the whole hall
// sensed at a glance instead of one camera at a time.
export function HallDigitalTwinGrid({ hall }: { hall: string }) {
  const { allCameras } = useHallScope()
  const allHallCameras = useMemo(() => allCameras.filter((c) => c.hall === hall), [allCameras, hall])
  const hallCameras = useMemo(() => allHallCameras.filter((c) => c.has_own_worker), [allHallCameras])

  // Fusion-secondary cameras (has_own_worker: false) have no frame loop of
  // their own to render a twin for, but they DO cover real seats — a
  // primary/secondary pair covering the same seat_1/seat_2 is exactly what
  // "dual coverage" means here, so the overlap check has to look at every
  // camera in the hall, not just the ones with their own twin to draw.
  const dualCoveredSeats = useMemo(() => {
    const count: Record<string, number> = {}
    for (const cam of allHallCameras) {
      for (const s of cam.seats) count[s] = (count[s] ?? 0) + 1
    }
    return Object.entries(count).filter(([, n]) => n > 1).map(([id]) => id)
  }, [allHallCameras])

  if (hallCameras.length === 0) {
    return <p className="text-xs text-white/30 mono px-1">no sensing-capable cameras deployed in {hall} yet</p>
  }

  return (
    <div>
      {dualCoveredSeats.length > 0 && (
        <div className="flex items-center gap-2 mb-3 text-[11px] mono text-watch px-3 py-2 rounded-lg border border-watch/25 bg-watch/8 w-fit">
          <Link2 size={12} />
          {dualCoveredSeats.length} seat{dualCoveredSeats.length === 1 ? '' : 's'} ({dualCoveredSeats.join(', ')}) sensed by more than
          one camera in {hall} — fused readings, redundant coverage
        </div>
      )}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {hallCameras.map((cam) => (
          <ClassroomDigitalTwin key={cam.camera_id} cameraId={cam.camera_id} />
        ))}
      </div>
    </div>
  )
}
