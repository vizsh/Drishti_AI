import { useEffect, useState, type ReactNode } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Link2, Fingerprint, UserRoundSearch, Activity, Compass, Shield, Camera } from 'lucide-react'
import { RiskTrendChart } from '../components/RiskTrendChart'
import { AlertFeed } from '../components/AlertFeed'
import { EvidenceModal } from '../components/EvidenceModal'
import { ActionDrawer } from '../components/ActionDrawer'
import { EmptyState } from '../components/EmptyState'
import { useLive } from '../state/LiveContext'
import { useHallScope } from '../state/useHallScope'
import { STATUS_COLOR, riskLevel } from '../lib/colors'
import { humanizeYaw, humanizeMotion, humanizeRisk, humanizeConfidence } from '../lib/humanize'
import type { AlertItem } from '../types'

interface EventRow {
  id: number
  seat_id: string
  event_type: string
  sim_time: number
  explanation: string | null
}

export function SeatDetailPage() {
  const { seatId } = useParams<{ seatId: string }>()
  const { seats, riskHistory, alerts, dismissAlert, dispatchInvigilator, acknowledgeAlert } = useLive()
  const { isSeatInScope } = useHallScope()
  const [evidenceUrl, setEvidenceUrl] = useState<string | null>(null)
  const [history, setHistory] = useState<EventRow[]>([])
  const [drawerAlert, setDrawerAlert] = useState<AlertItem | null>(null)

  useEffect(() => {
    if (!seatId) return
    fetch(`/api/events?seat_id=${seatId}&limit=200`)
      .then((r) => r.json())
      .then((d) => setHistory(d.events.filter((e: EventRow) => e.event_type !== 'telemetry')))
  }, [seatId])

  if (!seatId) return null

  if (!isSeatInScope(seatId)) {
    return (
      <div>
        <Link to="/overview" className="flex items-center gap-1.5 text-xs mono text-white/50 hover:text-white mb-4 w-fit">
          <ArrowLeft size={13} /> back to overview
        </Link>
        <div className="text-sm mono text-white/30 py-16 text-center">
          {seatId.toUpperCase()} is outside your assigned hall — access restricted.
        </div>
      </div>
    )
  }

  const seat = seats[seatId]
  const seatAlerts = alerts.filter((a) => a.seatId === seatId)
  const seatRiskHistory = riskHistory[seatId] ? { [seatId]: riskHistory[seatId] } : {}

  // Open the Action Drawer when an alert is clicked in the feed
  const handleAlertClick = (alert: AlertItem) => {
    setDrawerAlert(alert)
  }

  return (
    <div>
      <Link to="/overview" className="flex items-center gap-1.5 text-xs mono text-white/50 hover:text-white mb-4 w-fit">
        <ArrowLeft size={13} /> back to overview
      </Link>

      {!seat ? (
        <EmptyState
          icon={UserRoundSearch}
          title={`No data for ${seatId.replace('_', ' ').toUpperCase()} yet`}
          body="This seat hasn't been tracked yet this session — either it's empty, or the camera hasn't picked up a person there. It'll appear here automatically once it does."
        />
      ) : (
        <>
          <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold">{seatId.replace('_', ' ').toUpperCase()}</h1>
              <StatusBadge seat={seat} />
            </div>
            <Link
              to={`/twin/${seatId}`}
              className="flex items-center gap-1.5 text-[11px] mono px-3 py-1.5 rounded-full border border-white/15 text-white/60 hover:border-white/30 hover:text-white/90"
            >
              <Fingerprint size={12} /> behavioural profile
            </Link>
          </div>

          {/* Human-readable metrics — no raw z-scores in primary view */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <MetricCard
              icon={<Shield size={14} />}
              label="Status"
              value={seat.calibrated ? humanizeRisk(seat.risk) : 'Calibrating'}
              color={seat.calibrated ? STATUS_COLOR[riskLevel(seat.risk)] : '#8b8578'}
            />
            <MetricCard
              icon={<Compass size={14} />}
              label="Orientation"
              value={humanizeYaw(seat.yawZ)}
            />
            <MetricCard
              icon={<Activity size={14} />}
              label="Movement"
              value={humanizeMotion(seat.motionZ)}
            />
            <MetricCard
              icon={<Camera size={14} />}
              label="Detection quality"
              value={humanizeConfidence(seat.confidence).label}
              warn={humanizeConfidence(seat.confidence).warn}
              sublabel={seat.cameras && seat.cameras.length > 1
                ? `${seat.cameras.length} cameras fused`
                : undefined
              }
            />
          </div>

          {/* Technical details collapsed by default — for advanced users */}
          <details className="mb-6">
            <summary className="text-[10px] mono text-white/25 cursor-pointer hover:text-white/40 uppercase tracking-wider">
              Show technical telemetry
            </summary>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
              <RawMetric label="risk score" value={seat.calibrated ? seat.risk.toFixed(3) : '—'} />
              <RawMetric label="yaw_z" value={seat.yawZ != null ? seat.yawZ.toFixed(2) : '—'} />
              <RawMetric label="motion_z" value={seat.motionZ != null ? (seat.motionZ as number).toFixed(2) : '—'} />
              <RawMetric
                label="confidence"
                value={seat.confidence != null ? `${(seat.confidence * 100).toFixed(0)}%` : '—'}
              />
              <RawMetric
                label="camera source"
                value={seat.cameras && seat.cameras.length > 0 ? seat.cameras.join(' + ') : '—'}
              />
            </div>
          </details>

          <h2 className="text-sm font-bold uppercase tracking-wide mb-3">Risk trend — this seat, last 60s</h2>
          <div className="rounded-2xl border border-white/8 p-4 mb-6">
            <RiskTrendChart riskHistory={seatRiskHistory} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <AlertFeed
              alerts={seatAlerts}
              feedback={[]}
              seatIds={[seatId]}
              onDismiss={dismissAlert}
              onDispatch={dispatchInvigilator}
              onAcknowledge={acknowledgeAlert}
              onViewEvidence={setEvidenceUrl}
              onAlertClick={handleAlertClick}
            />
            <div>
              <h2 className="text-sm font-bold uppercase tracking-wide mb-3">Full history — this seat</h2>
              <div className="rounded-2xl border border-white/8 overflow-hidden overflow-y-auto" style={{ maxHeight: 560 }}>
                <table className="w-full text-xs">
                  <tbody>
                    {history.length === 0 && (
                      <tr><td className="px-4 py-6 text-center text-white/30 mono">no alert/gesture history for this seat yet</td></tr>
                    )}
                    {history.map((ev) => (
                      <tr key={ev.id} className="border-b border-white/5">
                        <td className="px-4 py-2 mono text-white/40 whitespace-nowrap">{ev.sim_time.toFixed(1)}s</td>
                        <td className="px-4 py-2 text-white/70">{ev.explanation ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}
      <EvidenceModal url={evidenceUrl} onClose={() => setEvidenceUrl(null)} />
      <ActionDrawer
        alert={drawerAlert}
        onClose={() => setDrawerAlert(null)}
        onDismiss={dismissAlert}
        onDispatch={dispatchInvigilator}
        onAcknowledge={acknowledgeAlert}
        onViewEvidence={setEvidenceUrl}
      />
    </div>
  )
}

function StatusBadge({ seat }: { seat: { calibrated: boolean; risk: number } }) {
  const level = seat.calibrated ? riskLevel(seat.risk) : null
  const color = level ? STATUS_COLOR[level] : '#8b8578'
  const label = seat.calibrated ? humanizeRisk(seat.risk) : 'Calibrating'
  return (
    <span className="text-xs mono uppercase px-3 py-1 rounded-full" style={{ background: `${color}22`, color }}>
      {label}
    </span>
  )
}

/** Human-readable metric card with icon */
function MetricCard({ icon, label, value, color, warn, sublabel }: {
  icon: ReactNode
  label: string
  value: string
  color?: string
  warn?: boolean
  sublabel?: string
}) {
  return (
    <div className="rounded-2xl border border-white/8 px-4 py-3">
      <div className="text-[10px] mono uppercase tracking-widest text-white/35 mb-1.5 flex items-center gap-1.5">
        {icon}
        {label}
      </div>
      <div className="text-base font-semibold" style={{ color: warn ? '#ffb648' : color }}>
        {value}
      </div>
      {sublabel && (
        <div className="text-[10px] mono text-white/30 mt-0.5 flex items-center gap-1">
          <Link2 size={10} /> {sublabel}
        </div>
      )}
    </div>
  )
}

/** Raw technical metric — only shown in collapsed "technical telemetry" section */
function RawMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/6 px-3 py-2">
      <div className="text-[9px] mono uppercase tracking-widest text-white/25 mb-0.5">{label}</div>
      <div className="text-xs mono text-white/50">{value}</div>
    </div>
  )
}
