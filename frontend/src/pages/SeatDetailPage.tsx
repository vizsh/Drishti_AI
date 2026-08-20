import { useEffect, useState, type ReactNode } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Link2, Eye, Fingerprint, UserRoundSearch } from 'lucide-react'
import { RiskTrendChart } from '../components/RiskTrendChart'
import { AlertFeed } from '../components/AlertFeed'
import { EvidenceModal } from '../components/EvidenceModal'
import { EmptyState } from '../components/EmptyState'
import { useLive } from '../state/LiveContext'
import { useHallScope } from '../state/useHallScope'
import { STATUS_COLOR, riskLevel } from '../lib/colors'

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

          {/* Everything that used to always render on the overview card now lives here */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <Metric label="risk score" value={seat.calibrated ? seat.risk.toFixed(2) : '—'} />
            <Metric label="yaw_z" value={seat.yawZ != null ? seat.yawZ.toFixed(2) : '—'} />
            <Metric
              label="detection confidence"
              value={seat.confidence != null ? `${(seat.confidence * 100).toFixed(0)}%` : '—'}
              icon={<Eye size={12} />}
              warn={seat.confidence != null && seat.confidence < 0.4}
            />
            <Metric
              label="camera source"
              value={seat.cameras && seat.cameras.length > 0 ? seat.cameras.join(' + ') : '—'}
              icon={seat.cameras.length > 1 ? <Link2 size={12} /> : undefined}
              small
            />
          </div>

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
    </div>
  )
}

function StatusBadge({ seat }: { seat: { calibrated: boolean; risk: number } }) {
  const level = seat.calibrated ? riskLevel(seat.risk) : null
  const color = level ? STATUS_COLOR[level] : '#8b8578'
  return (
    <span className="text-xs mono uppercase px-3 py-1 rounded-full" style={{ background: `${color}22`, color }}>
      {seat.calibrated ? level : 'calibrating'}
    </span>
  )
}

function Metric({ label, value, icon, warn, small }: { label: string; value: string; icon?: ReactNode; warn?: boolean; small?: boolean }) {
  return (
    <div className="rounded-2xl border border-white/8 px-4 py-3">
      <div className="text-[10px] mono uppercase tracking-widest text-white/35 mb-1 flex items-center gap-1">{icon}{label}</div>
      <div className={small ? 'text-xs mono text-white/70' : 'text-xl font-bold'} style={{ color: warn ? '#ffb648' : undefined }}>{value}</div>
    </div>
  )
}
