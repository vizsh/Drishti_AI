export interface SeatState {
  calibrated: boolean
  progress: number
  risk: number
  yawZ: number | null
  motionZ: number | null
  confidence: number | null
  cameras: string[]
  flash: boolean
}

export interface RiskPoint {
  t: number
  risk: number
}

export interface AlertItem {
  id: string
  kind: 'alert' | 'gesture'
  seatId: string
  timestamp: number
  riskScore?: number
  confidence?: number
  explanation: string
  objectLabel?: string | null
  evidenceUrl?: string | null
}

export interface WsEvent {
  type: string
  seat_id?: string
  timestamp?: number
  risk_score?: number
  yaw_z?: number | null
  motion_z?: number | null
  object_label?: string | null
  confidence?: number | null
  cameras?: string[]
  explanation?: string
  gesture?: string
  evidence_url?: string | null
  progress?: number
  image?: string
  wall_time?: number
  object_detector_finetuned?: boolean
  lighting_enhanced?: boolean
  message?: string
}
