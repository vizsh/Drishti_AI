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
  const [feedImage, setFeedImage] = useState<string | null>(null)
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

    function connect() {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${proto}://${location.host}/ws/live`)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        if (!cancelled) retryTimer = window.setTimeout(connect, 2000)
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
            },
            ...prev,
          ].slice(0, 60))
          flashSeat(ev.seat_id!)
          break
        }
        case 'feedback':
        case 'dispatch':
          setFeedback((prev) => [ev.message ?? '', ...prev].slice(0, 10))
          break
        case 'frame':
          if (ev.image) setFeedImage(`data:image/jpeg;base64,${ev.image}`)
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

  const dismissAlert = useCallback(async (seatId: string, resolution: string = 'false_alarm', invigilator?: string) => {
    await fetch(`/api/alerts/${seatId}/dismiss`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resolution, invigilator }),
    })
  }, [])

  const dispatchInvigilator = useCallback(async (seatId: string, invigilator: string) => {
    await fetch(`/api/alerts/${seatId}/dispatch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ invigilator }),
    })
  }, [])

  return {
    seats,
    riskHistory,
    alerts,
    connected,
    cameraOnline,
    detectorFinetuned,
    lightingEnhanced,
    feedImage,
    feedback,
    dismissAlert,
    dispatchInvigilator,
  }
}
