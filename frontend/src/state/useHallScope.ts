import { useEffect, useState } from 'react'
import { useAuth } from './AuthContext'

export interface CameraInfo {
  camera_id: string
  hall: string
  is_simulated: boolean
  is_primary: boolean
  seats: string[]
  streams_live_feed: boolean
  disconnected?: boolean
  video_paths?: string[]
  stream_mode?: 'off' | 'background' | 'focused'
  has_own_worker?: boolean
}

/**
 * Role-based hall scoping (Phase 1): a Controller sees every hall; an
 * Invigilator only ever sees their assigned hall's cameras/seats. This
 * hook is the single source of truth every later view (Live Monitor,
 * Examination Hall, Alerts, Evidence Vault) filters through, so scoping
 * stays consistent instead of being reimplemented per page.
 */
export function useHallScope() {
  const { user } = useAuth()
  const [cameras, setCameras] = useState<CameraInfo[]>([])

  function refreshCameras() {
    return fetch('/api/cameras')
      .then((r) => r.json())
      .then((d) => setCameras(d.cameras ?? []))
  }

  useEffect(() => {
    refreshCameras()
  }, [])

  const scopedCameras = user?.role === 'invigilator' ? cameras.filter((c) => c.hall === user.hall) : cameras

  const seatToHall: Record<string, string> = {}
  for (const cam of cameras) {
    for (const seat of cam.seats) seatToHall[seat] = cam.hall
  }

  const scopedSeatIds = new Set(scopedCameras.flatMap((c) => c.seats))
  const halls = [...new Set(cameras.map((c) => c.hall))].sort()

  function isSeatInScope(seatId: string): boolean {
    if (!user || user.role === 'controller') return true
    return scopedSeatIds.has(seatId)
  }

  return { cameras: scopedCameras, allCameras: cameras, seatToHall, scopedSeatIds, halls, isSeatInScope, refreshCameras }
}
