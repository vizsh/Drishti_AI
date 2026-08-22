import { useEffect, useRef, useState, useCallback } from 'react'
import type { SeatState, RiskPoint, AlertItem, WsEvent } from '../types'

const RISK_HISTORY_WINDOW_S = 60

export function useLiveSocket() {
  const [seats, setSeats] = useState<Record<string, SeatState>>({})
  const [riskHistory, setRiskHistory] = useState<Record<string, RiskPoint[]>>({})
  const [alerts, setAlerts] = useState<AlertItem[]>([])
  const [connected, setConnected] = useState(false)
  const [cameraOnline, setCameraOnline] = useState(false)
  const [detectorFinetuned, setDetectorFinetuned] = useState(false)
  const [lightingEnhanced, setLightingEnhanced] = useState(false)
  // Dashboard grid (2026-08-22): keyed by camera_id now that more than one
  // camera can stream at once — a single global feedImage silently meant
  // "whichever camera's frame arrived most recently overwrites every
  // tile," which only ever looked correct because only one camera was
  // ever actually streaming before this.
  const [feedImages, setFeedImages] = useState<Record<string, string>>({})
  const [feedback, setFeedback] = useState<string[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const lastHeartbeatRef = useRef(0)

  const flashSeat = useCallback((seatId: string) => {
    setSeats((prev) => {
      if (!prev[seatId]) return prev
      return { ...prev, [seatId]: { ...prev[seatId], flash: true } }
    })
    setTimeout(() => {
      setSeats((prev) => (prev[seatId] ? { ...prev, [seatId]: { ...prev[seatId], flash: false } } : prev))
    }, 1200)
  }, [])

  useEffect(() => {
    let cancelled = false
    let retryTimer: number
    let retryCount = 0

    function connect() {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${proto}://${location.host}/ws/live`)
      wsRef.current = ws

      ws.onopen = () => {
        retryCount = 0
        setConnected(true)
      }
      ws.onclose = (ev) => {
        setConnected(false)
        // 1008 = Policy Violation (unauthorized) — stop retrying, the user
        // needs to re-login. The auth context's 401 interceptor or session
        // rehydration will handle the redirect.
        if (ev.code === 1008 || cancelled) return
        // Exponential backoff: 2s, 4s, 8s … max 30s
        const delay = Math.min(2000 * Math.pow(2, retryCount), 30000)
        retryCount++
        retryTimer = window.setTimeout(connect, delay)
      }
      ws.onmessage = (msg) => {
        const ev: WsEvent = JSON.parse(msg.data)
        handleEvent(ev)
      }
    }

    function handleEvent(ev: WsEvent) {
      switch (ev.type) {
        case 'telemetry': {
          const seatId = ev.seat_id!
          setSeats((prev) => ({
            ...prev,
            [seatId]: {
              ...(prev[seatId] ?? { flash: false, progress: 0 }),
              calibrated: true,
              risk: ev.risk_score ?? 0,
              yawZ: ev.yaw_z ?? null,
              motionZ: ev.motion_z ?? null,
              confidence: ev.confidence ?? null,
              cameras: ev.cameras ?? [],
            },
          }))
          setRiskHistory((prev) => {
            const list = [...(prev[seatId] ?? []), { t: ev.timestamp ?? 0, risk: ev.risk_score ?? 0 }]
            const cutoff = (ev.timestamp ?? 0) - RISK_HISTORY_WINDOW_S
            return { ...prev, [seatId]: list.filter((p) => p.t >= cutoff) }
          })
          break
        }
        case 'calibrating': {
          const seatId = ev.seat_id!
          setSeats((prev) => ({
            ...prev,
            [seatId]: {
              ...(prev[seatId] ?? { flash: false, risk: 0, yawZ: null, motionZ: null, confidence: null, cameras: [] }),
              calibrated: false,
              progress: ev.progress ?? 0,
            },
          }))
          break
        }
        case 'alert': {
          setAlerts((prev) => [
            {
              id: `${ev.seat_id}-${ev.timestamp}`,
              kind: 'alert' as const,
              seatId: ev.seat_id!,
              timestamp: ev.timestamp ?? 0,
              riskScore: ev.risk_score,
              confidence: ev.confidence ?? undefined,
              explanation: ev.explanation ?? '',
              objectLabel: ev.object_label,
              evidenceUrl: ev.evidence_url,
              prosecution: ev.prosecution,
              defense: ev.defense,
              notify: ev.notify,
              occurrence: ev.occurrence,
              needsVerification: ev.needs_verification,
            },
            ...prev,
          ].slice(0, 60))
          flashSeat(ev.seat_id!)
          break
        }
        case 'gesture_alert': {
          setAlerts((prev) => [
            {
              id: `${ev.seat_id}-${ev.timestamp}-g`,
              kind: 'gesture' as const,
              seatId: ev.seat_id!,
              timestamp: ev.timestamp ?? 0,
              explanation: ev.explanation ?? '',
              notify: ev.notify,
              occurrence: ev.occurrence,
            },
            ...prev,
          ].slice(0, 60))
          flashSeat(ev.seat_id!)
          break
        }
        case 'calibration_warning': {
          setAlerts((prev) => [
            {
              id: `${ev.seat_id}-${ev.timestamp}-cw`,
              kind: 'calibration_warning' as const,
              seatId: ev.seat_id!,
              timestamp: ev.timestamp ?? 0,
              explanation: ev.explanation ?? '',
            },
            ...prev,
          ].slice(0, 60))
          break
        }
        case 'feedback':
        case 'dispatch':
        case 'acknowledge':
          setFeedback((prev) => [ev.message ?? '', ...prev].slice(0, 10))
          break
        case 'frame':
          if (ev.image && ev.camera_id) {
            const cameraId = ev.camera_id
            setFeedImages((prev) => ({ ...prev, [cameraId]: `data:image/jpeg;base64,${ev.image}` }))
          }
          break
        case 'heartbeat':
          lastHeartbeatRef.current = Date.now()
          setCameraOnline(true)
          if (ev.object_detector_finetuned !== undefined) setDetectorFinetuned(ev.object_detector_finetuned)
          setLightingEnhanced(!!ev.lighting_enhanced)
          break
      }
    }

    connect()
    const staleCheck = window.setInterval(() => {
      setCameraOnline(lastHeartbeatRef.current !== 0 && Date.now() - lastHeartbeatRef.current < 3000)
    }, 1000)

    return () => {
      cancelled = true
      window.clearTimeout(retryTimer)
      window.clearInterval(staleCheck)
      wsRef.current?.close()
    }
  }, [flashSeat])

  const dismissAlert = useCallback(async (
    seatId: string,
    resolution: string = 'false_alarm',
    invigilator?: string,
    signal?: { signalType: string; objectLabel?: string; confidence?: number }
  ) => {
    await fetch(`/api/alerts/${seatId}/dismiss`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        resolution,
        invigilator,
        signal_type: signal?.signalType,
        object_label: signal?.objectLabel,
        confidence: signal?.confidence,
      }),
    })
  }, [])

  const dispatchInvigilator = useCallback(async (seatId: string, invigilator: string) => {
    await fetch(`/api/alerts/${seatId}/dispatch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ invigilator }),
    })
  }, [])

  const acknowledgeAlert = useCallback(async (seatId: string, invigilator: string) => {
    await fetch(`/api/alerts/${seatId}/acknowledge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ invigilator }),
    })
  }, [])

  // Dashboard grid (2026-08-22): turns a camera's frame stream on/off/up —
  // see POST /api/cameras/{id}/stream. Silently no-ops on a 404 (a true
  // fusion-only secondary with no worker of its own to stream from) since
  // callers iterate every camera in scope and shouldn't need to know which
  // ones structurally can't stream.
  const setStreamMode = useCallback(async (cameraId: string, mode: 'off' | 'background' | 'focused') => {
    try {
      await fetch(`/api/cameras/${cameraId}/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
      })
    } catch {
      /* best-effort */
    }
  }, [])

  return {
    seats,
    riskHistory,
    alerts,
    connected,
    cameraOnline,
    detectorFinetuned,
    lightingEnhanced,
    feedImages,
    feedback,
    dismissAlert,
    dispatchInvigilator,
    acknowledgeAlert,
    setStreamMode,
  }
}
