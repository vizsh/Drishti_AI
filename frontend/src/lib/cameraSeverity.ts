import type { SeatState } from '../types'
import type { CameraInfo } from '../state/useHallScope'
import { riskLevel, type StatusLevel } from './colors'

export interface CameraSeverity {
  level: StatusLevel
  count: number
  worstSeat: string | null
}

// Dashboard grid (2026-08-22): extracted from CommandCenterPage's own
// local closure so the new Dashboard page (and anything else with a
// camera-tile grid) shares the exact same "worst seat on this camera"
// logic instead of quietly drifting into a second, subtly different
// definition of what counts as a flagged tile.
export function severityForCamera(cam: CameraInfo, seats: Record<string, SeatState>): CameraSeverity {
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
