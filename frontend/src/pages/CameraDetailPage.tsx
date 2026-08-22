import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Eye, LayoutGrid, Unplug, Plug, CameraOff, Film, Radar } from 'lucide-react'
import { useLive } from '../state/LiveContext'
import { useHallScope } from '../state/useHallScope'
import { RiskTrendChart } from '../components/RiskTrendChart'
import { AlertFeed } from '../components/AlertFeed'
import { EvidenceModal } from '../components/EvidenceModal'
import { EmptyState } from '../components/EmptyState'
import { ClassroomDigitalTwin } from '../components/ClassroomDigitalTwin'
import { severityForCamera } from '../lib/cameraSeverity'
import { STATUS_COLOR } from '../lib/colors'

type ViewMode = 'analytics' | 'watch' | 'twin'

interface EventRow {
  id: number
  seat_id: string
  event_type: string
  sim_time: number
  explanation: string | null
  evidence_url: string | null
}

// Product audit §7.2 (2026-08-22): the "actually watch this camera" screen
// that was missing entirely — clicking a tile used to jump straight to a
// seat's telemetry with no way to look at the footage itself, live or
// after the fact. This is the one screen that makes "you don't need a
// separate CCTV wall for this room" a credible claim: real video (the same
// focused-mode frame stream Lab Setup's room-scan already uses) next to
// the same real analytics every other page reads, plus a manual watch-only
// mode for when an invigilator just wants to look, and a scrub-a-recorded-
// clip mode over this camera's own evidence history.
export function CameraDetailPage() {
  const { cameraId } = useParams<{ cameraId: string }>()
  const navigate = useNavigate()
  const { seats, alerts, feedImages, riskHistory, setStreamMode, dismissAlert, dispatchInvigilator, acknowledgeAlert } = useLive()
  const { cameras, refreshCameras } = useHallScope()
  const [mode, setMode] = useState<ViewMode>('analytics')
  const [toggling, setToggling] = useState(false)
  const [history, setHistory] = useState<EventRow[]>([])
  const [evidenceUrl, setEvidenceUrl] = useState<string | null>(null)

  const cam = cameras.find((c) => c.camera_id === cameraId)

  useEffect(() => {
    if (!cameraId || !cam?.has_own_worker) return
    setStreamMode(cameraId, 'focused')
    return () => {
      setStreamMode(cameraId, 'background')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraId, cam?.has_own_worker])

  useEffect(() => {
    if (!cam || cam.seats.length === 0) return
    // Efficiency pass (2026-08-23): one batched request for every seat on
    // this camera instead of one fetch per seat (backend/main.py's
    // /api/events now accepts a comma-separated seat_id list).
    fetch(`/api/events?seat_id=${cam.seats.join(',')}&limit=${50 * cam.seats.length}`)
      .then((r) => r.json())
      .then((d) => {
        const merged = (d.events as EventRow[]).slice().sort((a, b) => b.sim_time - a.sim_time)
        setHistory(merged.filter((e) => e.event_type !== 'telemetry'))
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cam?.camera_id, cam?.seats.join(',')])

  const scopedAlerts = useMemo(
    () => (cam ? alerts.filter((a) => cam.seats.includes(a.seatId)) : []),
    [alerts, cam]
  )
  const clipHistory = useMemo(() => history.filter((h) => !!h.evidence_url), [history])
  const camRiskHistory = useMemo(
    () => (cam ? Object.fromEntries(cam.seats.filter((s) => riskHistory[s]).map((s) => [s, riskHistory[s]])) : {}),
    [cam, riskHistory]
  )

  async function toggleConnection() {
    if (!cam) return
    setToggling(true)
    try {
      const action = cam.disconnected ? 'reconnect' : 'disconnect'
      await fetch(`/api/setup/cameras/${cam.camera_id}/${action}`, { method: 'POST' })
      await refreshCameras()
    } finally {
      setToggling(false)
    }
  }

  if (!cameraId || !cam) {
    return (
      <EmptyState
        icon={CameraOff}
        title="Camera not found"
        body="This camera isn't in your access scope, or no longer exists in the current deployment."
      />
    )
  }

  const severity = severityForCamera(cam, seats)
  const snapshot = feedImages[cam.camera_id] ?? null

  return (
    <div>
      <button onClick={() => navigate('/dashboard')} className="flex items-center gap-1.5 text-xs mono text-white/50 hover:text-white mb-4 w-fit">
        <ArrowLeft size={13} /> back to Live Monitor
      </button>

      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <div>
          <h1 className="text-lg font-bold flex items-center gap-2">
            {cam.camera_id}
            <span className="text-[10px] mono uppercase tracking-wide px-2 py-0.5 rounded-full bg-white/8 text-white/50">
              {cam.hall}
            </span>
          </h1>
          <p className="text-xs mono text-white/35 mt-0.5">
            {cam.disconnected ? 'source disconnected' : cam.is_simulated ? 'simulated source' : 'real camera source'} ·{' '}
            {cam.seats.length} seat{cam.seats.length === 1 ? '' : 's'} covered
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border border-white/12 overflow-hidden">
            <button
              onClick={() => setMode('analytics')}
              className={`flex items-center gap-1.5 text-[11px] mono px-3 py-2 ${mode === 'analytics' ? 'bg-white/12 text-white' : 'text-white/50 hover:text-white/80'}`}
            >
              <LayoutGrid size={12} /> analytics view
            </button>
            <button
              onClick={() => setMode('watch')}
              className={`flex items-center gap-1.5 text-[11px] mono px-3 py-2 border-l border-white/12 ${mode === 'watch' ? 'bg-white/12 text-white' : 'text-white/50 hover:text-white/80'}`}
            >
              <Eye size={12} /> manual watch
            </button>
            <button
              onClick={() => setMode('twin')}
              className={`flex items-center gap-1.5 text-[11px] mono px-3 py-2 border-l border-white/12 ${mode === 'twin' ? 'bg-white/12 text-white' : 'text-white/50 hover:text-white/80'}`}
            >
              <Radar size={12} /> digital twin
            </button>
          </div>
          <button
            onClick={toggleConnection}
            disabled={toggling}
            className="flex items-center gap-1.5 text-[11px] mono uppercase px-3 py-2 rounded-lg border border-white/15 hover:border-white/30 text-white/70 disabled:opacity-50"
          >
            {cam.disconnected ? <Plug size={12} /> : <Unplug size={12} />}
            {toggling ? '…' : cam.disconnected ? 'reconnect' : 'disconnect'}
          </button>
        </div>
      </div>

      {mode === 'watch' ? (
        <div className="rounded-2xl overflow-hidden border border-white/8 bg-black flex items-center justify-center" style={{ aspectRatio: '16/9' }}>
          {cam.disconnected ? (
            <div className="text-center text-white/30">
              <Unplug size={28} className="mx-auto mb-2" />
              <p className="text-sm">source disconnected — reconnect to watch</p>
            </div>
          ) : snapshot ? (
            <img src={snapshot} className="max-w-full max-h-full object-contain" />
          ) : (
            <p className="text-sm text-white/30">waiting for frames…</p>
          )}
        </div>
      ) : mode === 'twin' ? (
        <ClassroomDigitalTwin cameraId={cam.camera_id} />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-5 mb-6">
          <div className="lg:col-span-3 rounded-2xl overflow-hidden border border-white/8 bg-black flex items-center justify-center relative" style={{ aspectRatio: '16/10' }}>
            {cam.disconnected ? (
              <div className="text-center text-white/30">
                <Unplug size={24} className="mx-auto mb-2" />
                <p className="text-xs">source disconnected</p>
              </div>
            ) : snapshot ? (
              <img src={snapshot} className="w-full h-full object-cover" />
            ) : (
              <p className="text-xs text-white/30">waiting for frames…</p>
            )}
            {!cam.disconnected && (
              <span
                className="absolute top-2 left-2 text-[9px] mono uppercase tracking-wide px-2 py-0.5 rounded-full"
                style={{ background: `${STATUS_COLOR[severity.level]}30`, color: STATUS_COLOR[severity.level] }}
              >
                {severity.level === 'calm' ? 'all calm' : `${severity.count} elevated`}
              </span>
            )}
          </div>
          <div className="lg:col-span-2 rounded-2xl border border-white/8 p-4">
            <div className="text-[10px] mono uppercase tracking-widest text-white/35 mb-2">this session, this camera</div>
            <div className="text-xs text-white/70 leading-relaxed mb-3">
              {scopedAlerts.filter((a) => a.kind === 'alert').length} alert{scopedAlerts.filter((a) => a.kind === 'alert').length === 1 ? '' : 's'} ·{' '}
              {scopedAlerts.filter((a) => a.kind === 'gesture').length} gesture event{scopedAlerts.filter((a) => a.kind === 'gesture').length === 1 ? '' : 's'} ·{' '}
              {clipHistory.length} evidence clip{clipHistory.length === 1 ? '' : 's'}
            </div>
            <div className="text-[10px] mono uppercase tracking-widest text-white/35 mb-1.5">risk trend — last 60s</div>
            <RiskTrendChart riskHistory={camRiskHistory} />
          </div>
        </div>
      )}

      {mode === 'analytics' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <AlertFeed
            alerts={scopedAlerts}
            feedback={[]}
            seatIds={cam.seats}
            onDismiss={dismissAlert}
            onDispatch={dispatchInvigilator}
            onAcknowledge={acknowledgeAlert}
            onViewEvidence={setEvidenceUrl}
          />
          <div>
            <h2 className="text-sm font-bold uppercase tracking-wide mb-3 flex items-center gap-2">
              <Film size={13} className="text-white/40" /> recorded window &mdash; scrub past clips
            </h2>
            <div className="rounded-2xl border border-white/8 overflow-hidden overflow-y-auto" style={{ maxHeight: 420 }}>
              {clipHistory.length === 0 ? (
                <p className="px-4 py-6 text-center text-xs text-white/30 mono">
                  no evidence clips captured for this camera yet — one gets recorded automatically when a real alert fires
                </p>
              ) : (
                <table className="w-full text-xs">
                  <tbody>
                    {clipHistory.map((ev) => (
                      <tr
                        key={ev.id}
                        onClick={() => setEvidenceUrl(ev.evidence_url as string)}
                        className="border-b border-white/5 last:border-b-0 cursor-pointer hover:bg-white/5"
                      >
                        <td className="px-4 py-2 mono text-white/40 whitespace-nowrap">{ev.seat_id.toUpperCase()}</td>
                        <td className="px-4 py-2 text-white/70">{ev.explanation ?? '—'}</td>
                        <td className="px-4 py-2 mono text-white/30 whitespace-nowrap text-right">{ev.sim_time.toFixed(0)}s</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}

      <EvidenceModal url={evidenceUrl} onClose={() => setEvidenceUrl(null)} />
    </div>
  )
}
