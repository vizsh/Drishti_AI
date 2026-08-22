import { useState } from 'react'
import { CoveragePanel } from '../components/CoveragePanel'
import { PatrolStatusPanel } from '../components/PatrolStatusPanel'
import { SeatGrid } from '../components/SeatGrid'
import { AlertFeed } from '../components/AlertFeed'
import { EvidenceModal } from '../components/EvidenceModal'
import { useLive } from '../state/LiveContext'
import { useHallScope } from '../state/useHallScope'

export function OverviewPage() {
  const { seats, alerts, feedback, dismissAlert, dispatchInvigilator, acknowledgeAlert } = useLive()
  const { isSeatInScope } = useHallScope()
  const [evidenceUrl, setEvidenceUrl] = useState<string | null>(null)

  const scopedSeats = Object.fromEntries(Object.entries(seats).filter(([id]) => isSeatInScope(id)))
  const seatIds = Object.keys(scopedSeats)
  const scopedAlerts = alerts.filter((a) => isSeatInScope(a.seatId))
  // Only a real, notify-worthy alert should visually flag a seat — not
  // every crossing of the raw risk score's watch/critical bands, which
  // happens constantly on ordinary movement.
  const alertedSeatIds = new Set(
    scopedAlerts.filter((a) => a.kind === 'alert' && a.notify !== false).map((a) => a.seatId)
  )

  return (
    <div>
      <CoveragePanel />
      <PatrolStatusPanel />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2">
          <h2 className="text-sm font-bold uppercase tracking-wide mb-3">Seating grid</h2>
          <SeatGrid seats={scopedSeats} alertedSeatIds={alertedSeatIds} />
        </div>
        <div className="lg:col-span-1">
          <AlertFeed
            alerts={scopedAlerts}
            feedback={feedback}
            seatIds={seatIds}
            onDismiss={dismissAlert}
            onDispatch={dispatchInvigilator}
            onAcknowledge={acknowledgeAlert}
            onViewEvidence={setEvidenceUrl}
            limit={8}
            showViewAllLink
          />
        </div>
      </div>
      <EvidenceModal url={evidenceUrl} onClose={() => setEvidenceUrl(null)} />
    </div>
  )
}
