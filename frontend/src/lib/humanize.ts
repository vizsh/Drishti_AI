/**
 * Converts raw z-scores and technical signals into plain-English behavior
 * descriptions that a non-technical invigilator can instantly understand.
 *
 * Product redesign (2026-08-21): z-scores are math concepts. Proctors need
 * descriptions of what the student is physically doing, not decimal values.
 */

/** Torso yaw z-score → human behavior description. */
export function humanizeYaw(yawZ: number | null): string {
  if (yawZ == null) return 'Facing forward'
  const abs = Math.abs(yawZ)
  const dir = yawZ > 0 ? 'right' : 'left'
  if (abs < 1.5) return 'Facing forward'
  if (abs < 2.5) return `Glancing ${dir}`
  if (abs < 4.0) return `Turned ${dir}`
  return `Looking far ${dir}`
}

/** Motion z-score → human movement description. */
export function humanizeMotion(motionZ: number | null): string {
  if (motionZ == null) return 'Settled'
  if (motionZ < 1.0) return 'Settled'
  if (motionZ < 2.0) return 'Minor movement'
  if (motionZ < 3.5) return 'Fidgeting'
  if (motionZ < 5.0) return 'High activity'
  return 'Repeated reaching'
}

/** Overall risk score → short status label for seat cards. */
export function humanizeRisk(risk: number): string {
  if (risk < 0.15) return 'All clear'
  if (risk < 0.25) return 'Normal activity'
  if (risk < 0.40) return 'Elevated activity'
  if (risk < 0.50) return 'Needs attention'
  if (risk < 0.70) return 'Verification required'
  return 'Immediate action'
}

/** Detection confidence → human-readable quality label. */
export function humanizeConfidence(confidence: number | null): {
  label: string
  warn: boolean
} {
  if (confidence == null) return { label: '—', warn: false }
  if (confidence < 0.3) return { label: 'Very low visibility', warn: true }
  if (confidence < 0.4) return { label: 'Low visibility', warn: true }
  if (confidence < 0.6) return { label: 'Moderate', warn: false }
  if (confidence < 0.8) return { label: 'Good', warn: false }
  return { label: 'Excellent', warn: false }
}

/** Calibration progress → user-friendly status message. */
export function humanizeCalibration(progress: number): string {
  if (progress < 0.3) return 'Learning this student\'s posture…'
  if (progress < 0.6) return 'Building behavior baseline…'
  if (progress < 0.9) return 'Finalizing baseline…'
  return 'Almost ready…'
}

/** Format a timestamp (seconds since session start) into a human-readable time. */
export function formatAlertTime(timestamp: number): string {
  const mins = Math.floor(timestamp / 60)
  const secs = Math.floor(timestamp % 60)
  if (mins === 0) return `${secs}s ago`
  return `${mins}m ${secs}s`
}
